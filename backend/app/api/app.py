from __future__ import annotations

import asyncio
import base64
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill
from backend.app.domain.ai_one_click_workflow import (
    AiOneClickWorkflow,
    AiSegmentationService,
    LangChainRoleAnalysisSkill,
    RoleAnalysisCandidate,
    create_whole_paragraph_utterance_drafts,
)
from backend.app.domain.ai_segmentation_agent import AiSegmentationAgent, LangChainSegmentationSkill
from backend.app.domain.audio import (
    DEFAULT_GENERATED_VOICE_TEXT,
    TTSServiceError,
    TTSTextLimitError,
    VoiceJob,
    build_tts_request,
    export_chapter_audio,
    generate_chapter_audio_batch,
    synthesize_local_qwen3,
    synthesize_local_qwen3_batch,
    synthesize_voice_design_qwen3,
)
from backend.app.domain.llm import MissingProviderCredential
from backend.app.domain.novel import Chapter, ChapterWorkbench, ParagraphModule, parse_novel_text
from backend.app.domain.novel_files import NovelFileError, extract_novel_file
from backend.app.domain.providers import default_provider_registry
from backend.app.domain.roles import RoleCard, RoleCollection, default_role_cards
from backend.app.domain.voices import (
    VoiceResource,
    VoiceResourceCollection,
    default_voice_resources,
    generated_voice_content,
)

ROOT = Path(__file__).resolve().parents[3]
LOCAL_DOTENV = dotenv_values(ROOT / ".env")
OUTPUT_AUDIO_DIR = ROOT / "outputs/audio"
OUTPUT_VOICE_RESOURCE_DIR = ROOT / "outputs/voice-resources"
OUTPUT_EXPORT_DIR = ROOT / "outputs/exports"
CHAPTER_PARSER_SCRIPT_DIR = ROOT / "scripts/chapter_parsers"
REAL_VOICE_ROOT = Path(os.environ.get("NOVELVOICE_REAL_VOICE_ROOT", "/Users/gaojing/Downloads/真实测试样本/音频"))
DEFAULT_TTS_SCRIPT = ROOT / "backend/tts/qwen3_tts_server.py"
DEFAULT_BASE_MODEL_PATH = "/Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-Base"
DEFAULT_VOICE_DESIGN_MODEL_PATH = "/Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
DEFAULT_TTS_STARTUP_TIMEOUT_SECONDS = 300.0


def _chapter_to_dict(chapter: Chapter) -> dict[str, Any]:
    return asdict(chapter)


def _paragraph_to_dict(paragraph) -> dict[str, Any]:
    return asdict(paragraph)


def _state(app: FastAPI) -> dict[str, Any]:
    return app.state.workflow


def _voice_to_dict(voice: VoiceResource) -> dict[str, Any]:
    return voice.to_dict()


def _resolve_audio_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def _is_inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _store_voice_resource_audio(path_text: str, *, voice_id: str) -> str:
    source = _resolve_audio_path(path_text)
    if not source.exists():
        raise HTTPException(status_code=400, detail=f"reference audio file does not exist: {path_text}")
    OUTPUT_VOICE_RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    if _is_inside(source, OUTPUT_VOICE_RESOURCE_DIR):
        return str(source.resolve())
    filename = _safe_audio_filename(f"{voice_id}{source.suffix}")
    target = OUTPUT_VOICE_RESOURCE_DIR / filename
    shutil.copy2(source, target)
    return str(target)


def _materialize_voice_resources(resources: list[VoiceResource]) -> list[VoiceResource]:
    materialized: list[VoiceResource] = []
    for voice in resources:
        try:
            reference_audio_path = _store_voice_resource_audio(
                voice.reference_audio_path,
                voice_id=voice.voice_id,
            )
        except HTTPException:
            reference_audio_path = voice.reference_audio_path
        materialized.append(
            voice.with_updates(
                reference_audio_path=reference_audio_path,
                playable_audio_path=voice.playable_audio_path or reference_audio_path,
            )
        )
    return materialized


def _default_model_config() -> dict[str, Any]:
    providers = default_provider_registry()
    siliconflow = providers["siliconflow-qwen3-8b"]
    deepseek = providers["deepseek-harness"]
    return {
        "llm": {
            "base_url": siliconflow["base_url"],
            "model": siliconflow["model"],
            "api_key": "",
        },
        "tts": {
            "base_url": os.environ.get("QWEN3_TTS_BASE_URL", "http://127.0.0.1:7811"),
            "model_path": os.environ.get("QWEN3_TTS_MODEL_PATH", DEFAULT_BASE_MODEL_PATH),
            "voice_design_model_path": os.environ.get(
                "QWEN3_TTS_VOICE_DESIGN_MODEL_PATH",
                DEFAULT_VOICE_DESIGN_MODEL_PATH,
            ),
        },
        "chapter_agent": {
            "base_url": deepseek["base_url"],
            "model": deepseek["model"],
            "api_key": "",
        },
    }


def _role_with_voice(role: RoleCard, voice: VoiceResource) -> RoleCard:
    return role.with_updates(
        voice_resource_id=voice.voice_id,
        reference_audio_path=voice.reference_audio_path,
        reference_text=voice.reference_text,
        design_prompt=None,
        voice_mode="voice_cloning",
        voice_description=voice.description,
        voice_sample_text=voice.reference_text,
        playable_voice_path=voice.playable_audio_path or voice.reference_audio_path,
        voice_generated_by_ai=voice.generated,
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
    app = FastAPI(title="NovelVoice-Agent v0.3.4 Harness API")
    OUTPUT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_VOICE_RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs/audio", StaticFiles(directory=OUTPUT_AUDIO_DIR), name="output_audio")
    app.mount("/outputs/exports", StaticFiles(directory=OUTPUT_EXPORT_DIR), name="output_exports")
    app.mount(
        "/outputs/voice-resources",
        StaticFiles(directory=OUTPUT_VOICE_RESOURCE_DIR),
        name="output_voice_resources",
    )
    voices = VoiceResourceCollection(_materialize_voice_resources(default_voice_resources(REAL_VOICE_ROOT)))
    app.state.workflow = {
        "chapters": [],
        "workbenches": {},
        "voices": voices,
        "roles": _seed_roles_from_voices(voices),
        "voice_jobs": {},
        "voice_previews": {},
        "tts_process": None,
        "model_config": _default_model_config(),
        "ai_one_click_workflows": {},
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

    @app.post("/api/novels/ai-chapter-split")
    async def ai_chapter_split(payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        return await _run_ai_chapter_split(app, text)

    @app.post("/api/novels/ai-chapter-split-file")
    async def ai_chapter_split_file(payload: dict[str, Any]) -> dict[str, Any]:
        filename = str(payload.get("filename") or "").strip()
        content_base64 = payload.get("content_base64")
        if not filename:
            raise HTTPException(status_code=400, detail="filename is required")
        if not isinstance(content_base64, str) or not content_base64.strip():
            raise HTTPException(status_code=400, detail="content_base64 is required")
        try:
            data = base64.b64decode(content_base64, validate=True)
            extracted = extract_novel_file(filename=filename, data=data)
        except (ValueError, NovelFileError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response = await _run_ai_chapter_split(app, extracted.text)
        response["source"] = {"filename": filename, "kind": extracted.kind}
        return response

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

    @app.put("/api/chapters/{chapter_id}/paragraphs")
    async def sync_chapter_paragraphs(chapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raw_paragraphs = payload.get("paragraphs")
        if not isinstance(raw_paragraphs, list):
            raise HTTPException(status_code=400, detail="paragraphs is required")
        paragraphs = [_paragraph_from_payload(item, index) for index, item in enumerate(raw_paragraphs, start=1)]
        visible = [paragraph for paragraph in paragraphs if not paragraph.deleted and paragraph.text.strip()]
        if not visible:
            raise HTTPException(status_code=400, detail="at least one visible paragraph is required")

        state = _state(app)
        existing = state["workbenches"].get(chapter_id)
        fallback_title = existing.chapter.title if existing else chapter_id
        title = str(payload.get("title") or fallback_title)
        body = "\n\n".join(paragraph.text for paragraph in visible)
        chapter = Chapter(chapter_id=chapter_id, title=title, body=body)
        workbench = ChapterWorkbench(chapter, paragraphs)
        if payload.get("confirm") is True:
            try:
                workbench.confirm_paragraphs()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        state["workbenches"][chapter_id] = workbench
        if not any(chapter.chapter_id == chapter_id for chapter in state["chapters"]):
            state["chapters"].append(chapter)
        response = {
            "chapter": _chapter_to_dict(chapter),
            "paragraphs": [_paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs],
            "can_segment": workbench.can_segment,
        }
        if payload.get("confirm") is True:
            response["utterance_drafts"] = create_whole_paragraph_utterance_drafts(
                workbench.visible_paragraphs
            )
        return response

    @app.post("/api/chapters/{chapter_id}/ai-one-click-analysis/start")
    async def start_ai_one_click_analysis(chapter_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        state = _state(app)
        workbench = state["workbenches"].get(chapter_id)
        if workbench is None:
            raise HTTPException(status_code=404, detail="chapter not found")
        workflow = _create_ai_one_click_workflow(app)
        try:
            result = workflow.start_role_analysis(
                chapter_id=chapter_id,
                chapter_title=workbench.chapter.title,
                paragraphs=[_paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs],
                existing_roles=[role.to_dict() for role in state["roles"].list()],
            )
        except MissingProviderCredential as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AI role analysis failed: {exc}") from exc
        state["ai_one_click_workflows"][result.thread_id] = workflow
        return result.to_dict()

    @app.post("/api/ai-one-click-analysis/{thread_id}/roles-completed")
    async def complete_ai_one_click_roles(thread_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        workflow = _ai_one_click_workflow(app, thread_id)
        roles = _roles_for_ai_one_click_payload(app, payload or {})
        try:
            result = workflow.resume_after_roles(
                thread_id=thread_id,
                roles=roles,
                existing_utterances_by_paragraph=_utterances_by_paragraph_from_payload(payload or {}),
            )
        except MissingProviderCredential as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AI one-click workflow failed: {exc}") from exc
        status_code = 422 if result.status == "failed" else 200
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=result.to_dict())
        return result.to_dict()

    @app.post("/api/ai-one-click-analysis/{thread_id}/roles-completed-stream")
    async def complete_ai_one_click_roles_stream(thread_id: str, payload: dict[str, Any] | None = None):
        workflow = _ai_one_click_workflow(app, thread_id)
        roles = _roles_for_ai_one_click_payload(app, payload or {})
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload or {})

        async def stream_events():
            events: queue.Queue[dict[str, Any]] = queue.Queue()

            def emit_role_selected(event: dict[str, Any]) -> None:
                events.put({"event": "role_selected", "data": event})

            def run_workflow() -> None:
                try:
                    result = workflow.resume_after_roles(
                        thread_id=thread_id,
                        roles=roles,
                        existing_utterances_by_paragraph=utterances_by_paragraph,
                        on_role_selected=emit_role_selected,
                    )
                    event_name = "completed" if result.status == "completed" else "failed"
                    events.put({"event": event_name, "data": result.to_dict()})
                except (MissingProviderCredential, KeyError, TypeError, ValueError, RuntimeError) as exc:
                    events.put({"event": "failed", "data": {"message": str(exc)}})

            threading.Thread(target=run_workflow, daemon=True).start()
            while True:
                item = await asyncio.to_thread(events.get)
                yield json.dumps(item, ensure_ascii=False) + "\n"
                if item["event"] in {"completed", "failed"}:
                    break

        return StreamingResponse(stream_events(), media_type="application/x-ndjson")

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
        provider = _segmentation_provider_from_config(app)
        try:
            agent_result = AiSegmentationAgent(
                skill=LangChainSegmentationSkill(
                    provider=provider,
                    api_key_lookup=_api_key_lookup_from_config(app),
                )
            ).segment(
                chapter_title=workbench.chapter.title,
                paragraph_id=paragraph_id,
                paragraph_text=paragraph.text,
                known_roles=roles,
            )
        except MissingProviderCredential as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM segmentation failed: {exc}") from exc
        result = agent_result.validation
        return {
            "ok": result.ok,
            "paragraph_id": result.paragraph_id,
            "utterances": result.utterances,
            "error_code": result.error_code,
            "error": result.error,
            "repaired": result.repaired,
            "raw_output": result.raw_output,
            "agent": {
                "reflection_count": agent_result.reflection_count,
                "trace": agent_result.trace,
            },
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

    @app.delete("/api/roles/{role_id}")
    async def delete_role(role_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        collection = _state(app)["roles"]
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload or {})
        result = collection.delete_with_policy(
            role_id,
            utterances_by_paragraph,
            action=str((payload or {}).get("action") or "block"),
            target_role_id=(payload or {}).get("target_role_id"),
        )
        status_code = 409 if not result.deleted and result.referenced_count else 200
        response = {
            "delete_result": result.to_dict(),
            "roles": [role.to_dict() for role in collection.list()],
            "role_options": collection.utterance_role_options(),
            "utterances_by_paragraph": utterances_by_paragraph,
        }
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=response)
        return response

    @app.get("/api/voice-resources")
    async def list_voice_resources() -> dict[str, Any]:
        voices = _state(app)["voices"]
        return {"voices": [_voice_to_dict(voice) for voice in voices.list()]}

    @app.post("/api/voice-resources")
    async def create_voice_resource(payload: dict[str, Any]) -> dict[str, Any]:
        voices = _state(app)["voices"]
        voice_id = str(payload.get("voice_id") or voices.next_id())
        reference_audio_path = _store_voice_resource_audio(
            _required_text(payload, "reference_audio_path"),
            voice_id=voice_id,
        )
        resource = voices.upsert(
            {
                "voice_id": voice_id,
                "name": _required_text(payload, "name"),
                "description": _required_text(payload, "description"),
                "reference_text": _required_text(payload, "reference_text"),
                "reference_audio_path": reference_audio_path,
                "generated": bool(payload.get("generated", False)),
                "gender": payload.get("gender"),
                "suitable_role_types": payload.get("suitable_role_types") or [],
                "playable_audio_path": payload.get("playable_audio_path") or reference_audio_path,
            }
        )
        return {"voice": _voice_to_dict(resource), "voices": [_voice_to_dict(voice) for voice in voices.list()]}

    @app.post("/api/voice-resources/reference-audio")
    async def upload_reference_audio(payload: dict[str, Any]) -> dict[str, Any]:
        filename = _safe_audio_filename(_required_text(payload, "filename"))
        data_base64 = _required_text(payload, "data_base64")
        try:
            audio_bytes = base64.b64decode(data_base64, validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="data_base64 must be valid base64") from exc
        target = OUTPUT_VOICE_RESOURCE_DIR / filename
        if target.exists():
            target = OUTPUT_VOICE_RESOURCE_DIR / f"{target.stem}-{len(list(OUTPUT_VOICE_RESOURCE_DIR.glob(target.stem + '*')))+1}{target.suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio_bytes)
        return {"filename": filename, "reference_audio_path": str(target)}

    @app.post("/api/voice-resources/generate")
    async def generate_voice_resource(payload: dict[str, Any]) -> dict[str, Any]:
        name = _required_text(payload, "name")
        description = _required_text(payload, "description")
        reference_text = str(payload.get("reference_text") or DEFAULT_GENERATED_VOICE_TEXT).strip()
        if not reference_text:
            reference_text = generated_voice_content(name, description)
        preview_id = f"preview-{len(_state(app)['voice_previews']) + 1:04d}"
        output_path = OUTPUT_VOICE_RESOURCE_DIR / f"{preview_id}.wav"
        design_request = {
            "input": reference_text,
            "instruct": description,
            "language": str(payload.get("language") or "Auto"),
            "response_format": "wav",
        }
        try:
            duration_seconds = synthesize_voice_design_qwen3(
                design_request,
                output_path=output_path,
                service_base_url=_state(app)["model_config"]["tts"].get("base_url"),
            )
            generation_status = "succeeded"
            generation_note = "已调用本地 Qwen3-TTS VoiceDesign 模型生成试听音色。"
            model_requirement = None
        except TTSServiceError as exc:
            duration_seconds = _write_substitute_wav(output_path)
            generation_status = "substitute"
            generation_note = f"没有成功调用 VoiceDesign 模型，已生成本地占位 wav 供流程预览：{exc}"
            model_requirement = (
                "需要下载并启动 Qwen3-TTS-12Hz-1.7B-VoiceDesign；"
                "当前 Qwen3-TTS-12Hz-1.7B-Base 主要支持有参考音频的 voice cloning。"
            )
        resource = VoiceResource(
            voice_id=preview_id,
            name=name,
            description=description,
            reference_text=reference_text,
            reference_audio_path=str(output_path),
            generated=True,
            gender=payload.get("gender"),
            suitable_role_types=[str(item) for item in payload.get("suitable_role_types") or []],
            playable_audio_path=str(output_path),
        )
        _state(app)["voice_previews"][preview_id] = resource
        return {
            "voice": _voice_to_dict(resource),
            "audio_url": f"/outputs/voice-resources/{preview_id}.wav",
            "duration_seconds": duration_seconds,
            "generation_status": generation_status,
            "generation_note": generation_note,
            "model_requirement": model_requirement,
        }

    @app.patch("/api/voice-resources/{voice_id}")
    async def update_voice_resource(voice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        voices = _state(app)["voices"]
        current = voices.get(voice_id)
        allowed = {
            key: value
            for key, value in payload.items()
            if key
            in {
                "name",
                "description",
                "reference_text",
                "reference_audio_path",
                "generated",
                "gender",
                "suitable_role_types",
                "playable_audio_path",
            }
        }
        if "reference_audio_path" in allowed:
            allowed["reference_audio_path"] = _store_voice_resource_audio(
                str(allowed["reference_audio_path"]),
                voice_id=voice_id,
            )
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
                key: value
                for key, value in payload["tts"].items()
                if key in {"base_url", "model_path", "voice_design_model_path"}
            }
            config["tts"] = {**config["tts"], **tts_updates}
        if isinstance(payload.get("chapter_agent"), dict):
            chapter_agent_updates = {
                key: value
                for key, value in payload["chapter_agent"].items()
                if key in {"base_url", "model", "api_key"}
            }
            config["chapter_agent"] = {**config["chapter_agent"], **chapter_agent_updates}
        return {"config": config}

    @app.post("/api/model-config/llm/test")
    async def test_remote_model_link(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config = {**_state(app)["model_config"]["llm"], **((payload or {}).get("llm") or {})}
        try:
            await _test_model_link(config)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"远端模型连接失败：{exc}") from exc
        return {"ok": True, "message": "远端模型连接成功"}

    @app.post("/api/model-config/chapter-agent/test")
    async def test_chapter_agent_model_link(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config = {
            **_state(app)["model_config"]["chapter_agent"],
            **((payload or {}).get("chapter_agent") or {}),
        }
        try:
            await _test_model_link(config, deepseek_compatible=True)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"章节划分智能体连接失败：{exc}") from exc
        return {"ok": True, "message": "章节划分智能体连接成功"}

    @app.post("/api/model-config/tts/start")
    async def start_local_tts_service(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config = {**_state(app)["model_config"]["tts"], **((payload or {}).get("tts") or {})}
        model_path = str(config.get("model_path") or "").strip()
        if not model_path:
            raise HTTPException(status_code=400, detail="model_path is required")
        voice_design_model_path = str(config.get("voice_design_model_path") or "").strip()
        base_url = str(config.get("base_url") or "http://127.0.0.1:7811")
        _state(app)["model_config"]["tts"] = config
        current = _state(app).get("tts_process")
        if current is not None and current.poll() is None:
            try:
                health = await asyncio.to_thread(_wait_for_tts_ready, current, base_url)
            except TimeoutError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            return {
                "ok": True,
                "message": "本地 TTS 服务已在运行，模型加载完成，VoiceDesign 已就绪",
                "pid": current.pid,
                "health": health,
                "progress": 100,
            }

        python_bin = os.environ.get("QWEN3_TTS_PYTHON", sys.executable)
        current_health = await asyncio.to_thread(_fetch_tts_health, base_url)
        if _is_tts_ready(current_health):
            return {
                "ok": True,
                "message": "本地 TTS 服务已在运行，模型加载完成，VoiceDesign 已就绪",
                "pid": None,
                "health": current_health,
                "progress": 100,
            }
        if current_health.get("reachable"):
            raise HTTPException(
                status_code=503,
                detail=_format_tts_not_ready_message(current_health),
            )

        port = _port_from_base_url(base_url)
        command = [
            python_bin,
            str(DEFAULT_TTS_SCRIPT),
            "--model-path",
            model_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--device",
            os.environ.get("QWEN3_TTS_DEVICE", "cpu"),
        ]
        if voice_design_model_path:
            command.extend(["--voice-design-model-path", voice_design_model_path])
        try:
            process = await asyncio.to_thread(_start_tts_process, command)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"本地 TTS 服务启动失败：{exc}") from exc
        _state(app)["tts_process"] = process
        try:
            health = await asyncio.to_thread(_wait_for_tts_ready, process, base_url)
        except TimeoutError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {
            "ok": True,
            "message": "本地 TTS 服务启动成功，模型加载完成，VoiceDesign 已就绪",
            "pid": process.pid,
            "health": health,
            "progress": 100,
        }

    @app.post("/api/utterances/{utterance_id}/speech")
    async def synthesize_speech(utterance_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        role_id = payload.get("role_id")
        if not role_id:
            raise HTTPException(status_code=400, detail="role_id is required")
        role = _speech_role_from_payload(app, _state(app)["roles"].get(str(role_id)), payload)
        utterance = {
            "utterance_id": utterance_id,
            "text": payload.get("text", ""),
            "voice_mode": payload.get("voice_mode", role.voice_mode),
            "design_prompt": payload.get("design_prompt"),
            "other_control_text": payload.get("other_control_text"),
            "emotion": payload.get("emotion"),
            "speed": payload.get("speed"),
            "volume": payload.get("volume"),
            "language": payload.get("language"),
            "x_vector_only": payload.get("x_vector_only"),
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
            emotion=str(request.get("emotion") or ""),
            speed=float(request.get("speed", 1.0)),
            volume=float(request.get("volume", 1.0)),
            language=str(request.get("language", "Auto")),
            other_control_text=request.get("other_control_text"),
            x_vector_only=bool(request.get("x_vector_only", False)),
        )
        try:
            duration_seconds = await asyncio.to_thread(
                synthesize_local_qwen3,
                request,
                output_path=output_path,
                service_base_url=_state(app)["model_config"]["tts"].get("base_url"),
            )
        except TTSTextLimitError as exc:
            error_job = VoiceJob(
                **{
                    **job.to_dict(),
                    "status": "failed",
                    "error": str(exc),
                }
            )
            _state(app)["voice_jobs"][job_id] = error_job
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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

    @app.post("/api/chapters/{chapter_id}/speech/batch")
    async def synthesize_chapter_speech_batch(chapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        roles = _roles_for_ai_one_click_payload(app, payload or {})
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload or {})

        def synthesize_group(request: dict[str, Any], *, output_dir: Path) -> list[dict[str, Any]]:
            output_paths = [
                output_dir / _safe_audio_filename(f"{statement_id}.wav")
                for statement_id in request["statement_ids"]
            ]
            try:
                return synthesize_local_qwen3_batch(
                    request,
                    output_paths=output_paths,
                    service_base_url=_state(app)["model_config"]["tts"].get("base_url"),
                )
            except TTSServiceError:
                results: list[dict[str, Any]] = []
                for statement_id, output_path in zip(request["statement_ids"], output_paths):
                    duration = _write_substitute_wav(output_path)
                    results.append(
                        {
                            "statement_id": statement_id,
                            "audio_path": str(output_path),
                            "audio_duration": duration,
                            "provider": "local-qwen3-tts-substitute",
                            "model": "deterministic-substitute",
                        }
                    )
                return results

        report = await asyncio.to_thread(
            generate_chapter_audio_batch,
            chapter_id=chapter_id,
            utterances_by_paragraph=utterances_by_paragraph,
            roles=roles,
            output_dir=OUTPUT_AUDIO_DIR,
            synthesize_batch=synthesize_group,
        )
        return report.to_dict()

    @app.post("/api/chapters/{chapter_id}/audio/export")
    async def export_chapter_audio_endpoint(chapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        roles = _roles_for_ai_one_click_payload(app, payload or {})
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload or {})
        chapter_title = str((payload or {}).get("chapter_title") or chapter_id)
        pause_ms = int((payload or {}).get("pause_ms") or 300)
        speed = float((payload or {}).get("speed") or 1.0)
        export_dir = OUTPUT_EXPORT_DIR / f"{_safe_audio_filename(chapter_id).removesuffix('.wav')}-{int(time.time())}"
        report = await asyncio.to_thread(
            export_chapter_audio,
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            utterances_by_paragraph=utterances_by_paragraph,
            roles=roles,
            output_dir=export_dir,
            pause_ms=pause_ms,
            speed=speed,
        )
        return report.to_dict()

    return app


async def _run_ai_chapter_split(app: FastAPI, text: str) -> dict[str, Any]:
    provider = _chapter_agent_provider_from_config(app)
    skill = ChapterSplitSkill(
        provider=provider,
        api_key_lookup=_chapter_agent_api_key_lookup_from_config(app),
    )
    agent = AiChapterSplitAgent(scripts_dir=CHAPTER_PARSER_SCRIPT_DIR, skill=skill)
    try:
        result = await asyncio.to_thread(agent.split, text)
    except MissingProviderCredential as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI chapter split failed: {exc}") from exc
    if not result.validation.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "AI chapter split validation failed",
                "errors": result.validation.errors,
                "trace": result.trace,
            },
        )

    state = _state(app)
    state["chapters"] = result.chapters
    state["workbenches"] = {
        chapter.chapter_id: ChapterWorkbench.from_chapter(chapter) for chapter in result.chapters
    }
    return {
        "chapters": [_chapter_to_dict(chapter) for chapter in result.chapters],
        "agent": {
            "status": result.status,
            "script_path": str(result.script_path) if result.script_path else None,
            "trace": result.trace,
            "validation_errors": result.validation.errors,
        },
    }


def _create_ai_one_click_workflow(app: FastAPI) -> AiOneClickWorkflow:
    role_provider = _chapter_agent_provider_from_config(app)
    segmentation_provider = _segmentation_provider_from_config(app)
    return AiOneClickWorkflow(
        role_skill=LangChainRoleAnalysisSkill(
            provider=role_provider,
            api_key_lookup=_chapter_agent_api_key_lookup_from_config(app),
        ),
        segmentation_service=AiSegmentationService(
            provider=segmentation_provider,
            api_key_lookup=_api_key_lookup_from_config(app),
        ),
        role_collection=_state(app)["roles"],
        voice_collection=_state(app)["voices"],
        voice_generator=lambda candidate: _generate_auto_voice_resource(app, candidate),
    )


def _generate_auto_voice_resource(app: FastAPI, candidate: RoleAnalysisCandidate) -> VoiceResource:
    voices = _state(app)["voices"]
    voice_id = f"voice-auto-{len(voices.list()) + 1:04d}"
    name = f"{candidate.name or '角色'}专属音色"
    description = candidate.voice_direction or candidate.profile or "AI自动生成音色"
    reference_text = generated_voice_content(name, description)
    output_path = OUTPUT_VOICE_RESOURCE_DIR / f"{voice_id}.wav"
    design_request = {
        "input": reference_text,
        "instruct": description,
        "language": "Auto",
        "response_format": "wav",
    }
    try:
        synthesize_voice_design_qwen3(
            design_request,
            output_path=output_path,
            service_base_url=_state(app)["model_config"]["tts"].get("base_url"),
        )
    except TTSServiceError:
        _write_substitute_wav(output_path)
    return VoiceResource(
        voice_id=voice_id,
        name=name,
        gender=candidate.gender,
        description=description,
        suitable_role_types=[item for item in [candidate.gender, candidate.profile] if item],
        reference_text=reference_text,
        reference_audio_path=str(output_path),
        playable_audio_path=str(output_path),
        generated=True,
    )


def _ai_one_click_workflow(app: FastAPI, thread_id: str) -> AiOneClickWorkflow:
    workflow = _state(app)["ai_one_click_workflows"].get(thread_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="AI one-click workflow thread not found")
    return workflow


def _roles_for_ai_one_click_payload(app: FastAPI, payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_roles = payload.get("roles")
    collection = _state(app)["roles"]
    if isinstance(raw_roles, list):
        for raw_role in raw_roles:
            if isinstance(raw_role, dict) and raw_role.get("role_id"):
                collection.upsert(_role_payload_with_resource(app, raw_role))
    return [role.to_dict() for role in collection.list()]


def _utterances_by_paragraph_from_payload(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw = payload.get("utterances_by_paragraph")
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, list[dict[str, Any]]] = {}
    for paragraph_id, utterances in raw.items():
        if not isinstance(utterances, list):
            continue
        normalized[str(paragraph_id)] = [dict(item) for item in utterances if isinstance(item, dict)]
    return normalized


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


def _paragraph_from_payload(payload: Any, index: int) -> ParagraphModule:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="paragraph item must be an object")
    text = str(payload.get("text") or "").strip()
    return ParagraphModule(
        paragraph_id=str(payload.get("paragraph_id") or f"p-{index:04d}"),
        text=text,
        collapsed=bool(payload.get("collapsed", False)),
        deleted=bool(payload.get("deleted", False)),
        confirmed=bool(payload.get("confirmed", False)),
    )


def _segmentation_provider_from_config(app: FastAPI) -> dict[str, Any]:
    provider = default_provider_registry()["siliconflow-qwen3-8b"]
    config = _state(app)["model_config"]["llm"]
    provider["base_url"] = config.get("base_url") or provider["base_url"]
    provider["model"] = config.get("model") or provider["model"]
    return provider


def _api_key_lookup_from_config(app: FastAPI):
    def lookup(name: str) -> str | None:
        configured = str(_state(app)["model_config"]["llm"].get("api_key") or "").strip()
        return configured or os.environ.get(name)

    return lookup


def _chapter_agent_provider_from_config(app: FastAPI) -> dict[str, Any]:
    provider = default_provider_registry()["deepseek-harness"]
    config = _state(app)["model_config"]["chapter_agent"]
    provider["base_url"] = _deepseek_base_url(config.get("base_url") or provider["base_url"])
    provider["model"] = config.get("model") or provider["model"]
    return provider


def _chapter_agent_api_key_lookup_from_config(app: FastAPI):
    def lookup(name: str) -> str | None:
        configured = str(_state(app)["model_config"]["chapter_agent"].get("api_key") or "").strip()
        dotenv_value = LOCAL_DOTENV.get(name)
        return configured or os.environ.get(name) or (str(dotenv_value).strip() if dotenv_value else None)

    return lookup


def _safe_audio_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
        suffix = ".wav"
    stem = Path(filename).stem
    stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", stem).strip("-") or "reference-audio"
    return f"{stem}{suffix}"


def _port_from_base_url(base_url: str) -> int:
    match = re.search(r":(\d+)(?:/)?$", base_url.rstrip("/"))
    return int(match.group(1)) if match else 7811


def _test_models_endpoint(request: urllib.request.Request) -> None:
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


def _deepseek_base_url(base_url: str) -> str:
    return str(base_url or "").rstrip("/").removesuffix("/v1")


async def _test_model_link(config: dict[str, Any], *, deepseek_compatible: bool = False) -> None:
    base_url = str(config.get("base_url") or "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")
    models_base_url = _deepseek_base_url(base_url) if deepseek_compatible else base_url
    headers = {"Content-Type": "application/json"}
    api_key = str(config.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(f"{models_base_url}/models", headers=headers, method="GET")
    await asyncio.to_thread(_test_models_endpoint, request)


def _start_tts_process(command: list[str]) -> subprocess.Popen:
    return subprocess.Popen(command, cwd=str(ROOT))


def _tts_startup_timeout_seconds() -> float:
    raw_value = os.environ.get("NOVELVOICE_TTS_STARTUP_TIMEOUT_SECONDS", "")
    if not raw_value:
        return DEFAULT_TTS_STARTUP_TIMEOUT_SECONDS
    try:
        return max(0.01, float(raw_value))
    except ValueError:
        return DEFAULT_TTS_STARTUP_TIMEOUT_SECONDS


def _tts_root_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    return root.removesuffix("/v1")


def _fetch_tts_health(base_url: str) -> dict[str, Any]:
    health_url = f"{_tts_root_url(base_url)}/health"
    request = urllib.request.Request(health_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {
            "reachable": False,
            "ready": False,
            "error": str(exc),
            "health_url": health_url,
        }
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    return {
        **payload,
        "reachable": True,
        "ready": _is_tts_ready(payload),
        "health_url": health_url,
    }


def _is_tts_ready(health: dict[str, Any]) -> bool:
    return (
        bool(health.get("ok"))
        and bool(health.get("voice_clone"))
        and bool(health.get("voice_design"))
        and bool(health.get("voice_design_capable"))
    )


def _format_tts_not_ready_message(health: dict[str, Any]) -> str:
    if health.get("reachable"):
        return (
            "本地 TTS 服务尚未完成启动：模型加载未完成或 VoiceDesign 模型未就绪；"
            "请确认 Qwen3-TTS-12Hz-1.7B-VoiceDesign 权重路径正确，并等待启动进度完成。"
        )
    return (
        "本地 TTS 服务尚未完成启动：模型加载仍在进行或服务端口暂未响应；"
        f"最近一次健康检查错误：{health.get('error', 'unknown')}"
    )


def _wait_for_tts_ready(
    process: subprocess.Popen | None,
    base_url: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    timeout = _tts_startup_timeout_seconds() if timeout_seconds is None else timeout_seconds
    deadline = time.monotonic() + timeout
    last_health: dict[str, Any] = {"reachable": False, "error": "health check has not run"}
    while True:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"本地 TTS 服务启动失败：进程已退出，退出码 {process.poll()}")
        last_health = _fetch_tts_health(base_url)
        if _is_tts_ready(last_health):
            return last_health
        if time.monotonic() >= deadline:
            raise TimeoutError(_format_tts_not_ready_message(last_health))
        time.sleep(min(1.0, max(0.01, deadline - time.monotonic())))


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


def _speech_role_from_payload(app: FastAPI, role: RoleCard, payload: dict[str, Any]) -> RoleCard:
    voice_resource_id = payload.get("voice_resource_id")
    if not voice_resource_id:
        return role
    try:
        voice = _state(app)["voices"].get(str(voice_resource_id))
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="voice resource not found") from exc
    return _role_with_voice(role, voice)
