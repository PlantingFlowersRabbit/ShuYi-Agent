from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from backend.app.domain.audio import (
    TTSServiceError,
    VoiceJob,
    build_tts_request,
    synthesize_local_qwen3,
)
from backend.app.domain.llm import MissingProviderCredential, OpenAICompatibleSegmentationClient
from backend.app.domain.novel import Chapter, ChapterWorkbench, parse_novel_text
from backend.app.domain.providers import default_provider_registry
from backend.app.domain.roles import RoleCollection, default_role_cards
from backend.app.domain.segmentation import repair_json_output_once, validate_segmentation_result

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_AUDIO_DIR = ROOT / "outputs/audio"


def _chapter_to_dict(chapter: Chapter) -> dict[str, Any]:
    return asdict(chapter)


def _paragraph_to_dict(paragraph) -> dict[str, Any]:
    return asdict(paragraph)


def _state(app: FastAPI) -> dict[str, Any]:
    return app.state.workflow


def create_app() -> FastAPI:
    app = FastAPI(title="NovelVoice-Agent v0.1 Manual Collaboration API")
    OUTPUT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs/audio", StaticFiles(directory=OUTPUT_AUDIO_DIR), name="output_audio")
    app.state.workflow = {
        "chapters": [],
        "workbenches": {},
        "roles": RoleCollection(default_role_cards()),
        "voice_jobs": {},
    }

    @app.post("/api/novels/parse")
    async def parse_novel(payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        chapters = parse_novel_text(text)
        state = _state(app)
        state["chapters"] = chapters
        state["workbenches"] = {
            chapter.chapter_id: ChapterWorkbench.from_chapter(chapter) for chapter in chapters
        }
        return {"chapters": [_chapter_to_dict(chapter) for chapter in chapters]}

    @app.get("/api/chapters")
    async def list_chapters() -> dict[str, Any]:
        return {"chapters": [_chapter_to_dict(chapter) for chapter in _state(app)["chapters"]]}

    @app.get("/api/chapters/{chapter_id}")
    async def get_chapter(chapter_id: str) -> dict[str, Any]:
        state = _state(app)
        workbench = state["workbenches"].get(chapter_id)
        if workbench is None:
            raise HTTPException(status_code=404, detail="chapter not found")
        return {
            "chapter": _chapter_to_dict(workbench.chapter),
            "paragraphs": [_paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs],
            "can_segment": workbench.can_segment,
        }

    @app.patch("/api/paragraphs/{paragraph_id}")
    async def update_paragraph(paragraph_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        workbench = _find_workbench_for_paragraph(app, paragraph_id)
        if "text" in payload:
            workbench.edit_paragraph(paragraph_id, str(payload["text"]))
        if payload.get("deleted") is True:
            workbench.delete_paragraph(paragraph_id)
        if payload.get("toggle") is True:
            workbench.toggle_paragraph(paragraph_id)
        if payload.get("confirm_all") is True:
            workbench.confirm_paragraphs()
        return {
            "paragraphs": [_paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs],
            "can_segment": workbench.can_segment,
        }

    @app.post("/api/paragraphs/{paragraph_id}/segment")
    async def segment_paragraph(paragraph_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        workbench = _find_workbench_for_paragraph(app, paragraph_id)
        if not workbench.can_segment:
            raise HTTPException(status_code=409, detail="paragraphs must be confirmed before segmentation")
        paragraph = workbench.get_paragraph(paragraph_id)
        roles = [role.to_dict() for role in _state(app)["roles"].list()]
        provider = default_provider_registry()["siliconflow-qwen3-8b"]
        try:
            raw_output = OpenAICompatibleSegmentationClient(provider=provider).segment(
                chapter_title=workbench.chapter.title,
                paragraph_id=paragraph_id,
                paragraph_text=paragraph.text,
                known_roles=roles,
            )
        except MissingProviderCredential as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM segmentation failed: {exc}") from exc
        result = validate_segmentation_result(
            paragraph_id=paragraph_id,
            paragraph_text=paragraph.text,
            raw_output=str(raw_output),
            known_roles=roles,
            repair_json=repair_json_output_once,
        )
        return {
            "ok": result.ok,
            "paragraph_id": result.paragraph_id,
            "utterances": result.utterances,
            "error_code": result.error_code,
            "error": result.error,
            "repaired": result.repaired,
            "raw_output": result.raw_output,
        }

    @app.api_route("/api/roles", methods=["GET", "POST"])
    async def roles(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        collection = _state(app)["roles"]
        if payload:
            collection.upsert(payload)
        return {
            "roles": [role.to_dict() for role in collection.list()],
            "role_options": collection.utterance_role_options(),
        }

    @app.patch("/api/roles/{role_id}")
    async def update_role(role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        collection = _state(app)["roles"]
        current = collection.get(role_id)
        updated = current.with_updates(**{**payload, "role_id": role_id})
        collection.upsert(updated)
        return {
            "role": updated.to_dict(),
            "role_options": collection.utterance_role_options(),
        }

    @app.post("/api/utterances/{utterance_id}/speech")
    async def synthesize_speech(utterance_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        role_id = payload.get("role_id")
        if not role_id:
            raise HTTPException(status_code=400, detail="role_id is required")
        role = _state(app)["roles"].get(str(role_id))
        utterance = {
            "utterance_id": utterance_id,
            "text": payload.get("text", ""),
            "voice_mode": payload.get("voice_mode", role.voice_mode),
            "design_prompt": payload.get("design_prompt"),
        }
        try:
            request = build_tts_request(utterance, role)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        job_id = f"vj-{len(_state(app)['voice_jobs']) + 1:04d}"
        output_path = OUTPUT_AUDIO_DIR / f"{job_id}.wav"
        relative_output_path = f"outputs/audio/{job_id}.wav"
        job = VoiceJob(
            voice_job_id=job_id,
            utterance_id=utterance_id,
            role_id=role.role_id,
            voice_mode=utterance["voice_mode"],
            provider="local-qwen3-tts",
            request_text=request["input"],
            reference_audio_path=request.get("audio_sample_path"),
            reference_text=request.get("ref_text"),
            response_format=request.get("response_format", "wav"),
            output_path=relative_output_path,
            status="succeeded",
            error=None,
        )
        try:
            duration_seconds = synthesize_local_qwen3(request, output_path=output_path)
        except TTSServiceError as exc:
            failed_job = VoiceJob(
                **{
                    **job.to_dict(),
                    "status": "failed",
                    "error": str(exc),
                }
            )
            _state(app)["voice_jobs"][job_id] = failed_job
            raise HTTPException(status_code=502, detail=failed_job.to_dict()) from exc

        _state(app)["voice_jobs"][job_id] = job
        return {
            "voice_job": job.to_dict(),
            "audio_url": f"/outputs/audio/{job_id}.wav",
            "duration_seconds": duration_seconds,
        }

    return app


def _find_workbench_for_paragraph(app: FastAPI, paragraph_id: str) -> ChapterWorkbench:
    for workbench in _state(app)["workbenches"].values():
        try:
            workbench.get_paragraph(paragraph_id)
        except KeyError:
            continue
        return workbench
    raise HTTPException(status_code=404, detail="paragraph not found")
