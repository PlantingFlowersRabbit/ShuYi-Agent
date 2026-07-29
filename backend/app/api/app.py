from __future__ import annotations

import os
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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
from backend.app.domain.roles import RoleCard, RoleCollection, default_role_cards
from backend.app.domain.segmentation import repair_json_output_once, validate_segmentation_result
from backend.app.domain.voices import (
    BUILTIN_REFERENCE_AUDIO,
    VoiceResource,
    VoiceResourceCollection,
    default_voice_resources,
    generated_voice_content,
)

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_AUDIO_DIR = ROOT / "outputs/audio"
REAL_VOICE_ROOT = Path(os.environ.get("NOVELVOICE_REAL_VOICE_ROOT", "/Users/gaojing/Downloads/真实测试样本/音频"))


def _chapter_to_dict(chapter: Chapter) -> dict[str, Any]:
    return asdict(chapter)


def _paragraph_to_dict(paragraph) -> dict[str, Any]:
    return asdict(paragraph)


def _state(app: FastAPI) -> dict[str, Any]:
    return app.state.workflow


def _voice_to_dict(voice: VoiceResource) -> dict[str, Any]:
    return voice.to_dict()


def _default_model_config() -> dict[str, Any]:
    providers = default_provider_registry()
    siliconflow = providers["siliconflow-qwen3-8b"]
    return {
        "llm": {
            "base_url": siliconflow["base_url"],
            "model": siliconflow["model"],
            "api_key": "",
        },
        "tts": {
            "base_url": os.environ.get("QWEN3_TTS_BASE_URL", "http://127.0.0.1:7811"),
            "model_path": os.environ.get("QWEN3_TTS_MODEL_PATH", ""),
        },
    }


def _role_with_voice(role: RoleCard, voice: VoiceResource) -> RoleCard:
    return role.with_updates(
        voice_resource_id=voice.voice_id,
        reference_audio_path=voice.reference_audio_path,
        reference_text=voice.reference_text,
        design_prompt=None,
        voice_mode="voice_cloning",
    )


def _seed_roles_from_voices(voices: VoiceResourceCollection) -> RoleCollection:
    roles = []
    for role in default_role_cards():
        if role.voice_resource_id:
            try:
                roles.append(_role_with_voice(role, voices.get(role.voice_resource_id)))
                continue
            except KeyError:
                pass
        roles.append(role)
    return RoleCollection(roles)


def create_app() -> FastAPI:
    app = FastAPI(title="NovelVoice-Agent v0.13 Harness API")
    OUTPUT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs/audio", StaticFiles(directory=OUTPUT_AUDIO_DIR), name="output_audio")
    voices = VoiceResourceCollection(default_voice_resources(REAL_VOICE_ROOT))
    app.state.workflow = {
        "chapters": [],
        "workbenches": {},
        "voices": voices,
        "roles": _seed_roles_from_voices(voices),
        "voice_jobs": {},
        "model_config": _default_model_config(),
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
            collection.upsert(_role_payload_with_resource(app, payload))
        return {
            "roles": [role.to_dict() for role in collection.list()],
            "role_options": collection.utterance_role_options(),
        }

    @app.patch("/api/roles/{role_id}")
    async def update_role(role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        collection = _state(app)["roles"]
        current = collection.get(role_id)
        updates = _role_payload_with_resource(app, {**payload, "role_id": role_id})
        updated = current.with_updates(**updates)
        collection.upsert(updated)
        return {
            "role": updated.to_dict(),
            "role_options": collection.utterance_role_options(),
        }

    @app.get("/api/voice-resources")
    async def list_voice_resources() -> dict[str, Any]:
        voices = _state(app)["voices"]
        return {"voices": [_voice_to_dict(voice) for voice in voices.list()]}

    @app.post("/api/voice-resources")
    async def create_voice_resource(payload: dict[str, Any]) -> dict[str, Any]:
        voices = _state(app)["voices"]
        resource = voices.upsert(
            {
                "voice_id": payload.get("voice_id") or voices.next_id(),
                "name": _required_text(payload, "name"),
                "description": _required_text(payload, "description"),
                "reference_text": _required_text(payload, "reference_text"),
                "reference_audio_path": _required_text(payload, "reference_audio_path"),
                "generated": bool(payload.get("generated", False)),
            }
        )
        return {"voice": _voice_to_dict(resource), "voices": [_voice_to_dict(voice) for voice in voices.list()]}

    @app.post("/api/voice-resources/generate")
    async def generate_voice_resource(payload: dict[str, Any]) -> dict[str, Any]:
        voices = _state(app)["voices"]
        name = _required_text(payload, "name")
        description = _required_text(payload, "description")
        resource = voices.upsert(
            {
                "voice_id": payload.get("voice_id") or voices.next_id(),
                "name": name,
                "description": description,
                "reference_text": generated_voice_content(name, description),
                "reference_audio_path": str(payload.get("reference_audio_path") or BUILTIN_REFERENCE_AUDIO),
                "generated": True,
            }
        )
        return {
            "voice": _voice_to_dict(resource),
            "voices": [_voice_to_dict(voice) for voice in voices.list()],
            "generation_note": "local deterministic substitute; not a real voice design quality claim",
        }

    @app.patch("/api/voice-resources/{voice_id}")
    async def update_voice_resource(voice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        voices = _state(app)["voices"]
        current = voices.get(voice_id)
        allowed = {
            key: value
            for key, value in payload.items()
            if key in {"name", "description", "reference_text", "reference_audio_path", "generated"}
        }
        updated = current.with_updates(**allowed)
        voices.upsert(updated)
        return {"voice": _voice_to_dict(updated), "voices": [_voice_to_dict(voice) for voice in voices.list()]}

    @app.get("/api/voice-resources/{voice_id}/audio")
    async def get_voice_resource_audio(voice_id: str):
        voice = _state(app)["voices"].get(voice_id)
        audio_path = Path(voice.reference_audio_path)
        if not audio_path.is_absolute():
            audio_path = ROOT / audio_path
        if not audio_path.exists():
            raise HTTPException(status_code=404, detail="reference audio not found")
        return FileResponse(audio_path)

    @app.delete("/api/voice-resources/{voice_id}")
    async def delete_voice_resource(voice_id: str) -> dict[str, Any]:
        voices = _state(app)["voices"]
        voices.remove(voice_id)
        return {"voices": [_voice_to_dict(voice) for voice in voices.list()]}

    @app.get("/api/model-config")
    async def get_model_config() -> dict[str, Any]:
        return {"config": _state(app)["model_config"]}

    @app.patch("/api/model-config")
    async def update_model_config(payload: dict[str, Any]) -> dict[str, Any]:
        config = _state(app)["model_config"]
        if isinstance(payload.get("llm"), dict):
            llm_updates = {
                key: value
                for key, value in payload["llm"].items()
                if key in {"base_url", "model", "api_key"}
            }
            config["llm"] = {**config["llm"], **llm_updates}
        if isinstance(payload.get("tts"), dict):
            tts_updates = {
                key: value for key, value in payload["tts"].items() if key in {"base_url", "model_path"}
            }
            config["tts"] = {**config["tts"], **tts_updates}
        return {"config": config}

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
            duration_seconds = _write_substitute_wav(output_path)
            substitute_job = VoiceJob(
                **{
                    **job.to_dict(),
                    "status": "substitute",
                    "error": f"本地 Qwen3-TTS 不可用，已生成本地可播放占位音频：{exc}",
                }
            )
            _state(app)["voice_jobs"][job_id] = substitute_job
            return {
                "voice_job": substitute_job.to_dict(),
                "audio_url": f"/outputs/audio/{job_id}.wav",
                "duration_seconds": duration_seconds,
                "warning": "local TTS service unavailable; returned a deterministic substitute wav",
            }

        _state(app)["voice_jobs"][job_id] = job
        return {
            "voice_job": job.to_dict(),
            "audio_url": f"/outputs/audio/{job_id}.wav",
            "duration_seconds": duration_seconds,
        }

    return app


def _write_substitute_wav(path: Path, *, duration_seconds: float = 0.75, sample_rate: int = 16000) -> float:
    frame_count = int(duration_seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return duration_seconds


def _find_workbench_for_paragraph(app: FastAPI, paragraph_id: str) -> ChapterWorkbench:
    for workbench in _state(app)["workbenches"].values():
        try:
            workbench.get_paragraph(paragraph_id)
        except KeyError:
            continue
        return workbench
    raise HTTPException(status_code=404, detail="paragraph not found")


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{field} is required")
    return value.strip()


def _role_payload_with_resource(app: FastAPI, payload: dict[str, Any]) -> dict[str, Any]:
    updates = dict(payload)
    voice_resource_id = updates.get("voice_resource_id")
    if voice_resource_id:
        voice = _state(app)["voices"].get(str(voice_resource_id))
        updates["reference_audio_path"] = voice.reference_audio_path
        updates["reference_text"] = voice.reference_text
        updates["design_prompt"] = None
        updates["voice_mode"] = "voice_cloning"
    return updates
