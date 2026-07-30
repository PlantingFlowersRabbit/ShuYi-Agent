from __future__ import annotations

import asyncio
import base64
import os
import re
import subprocess
import sys
import urllib.request
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill
from backend.app.domain.audio import (
    DEFAULT_GENERATED_VOICE_TEXT,
    TTSServiceError,
    VoiceJob,
    build_tts_request,
    synthesize_local_qwen3,
    synthesize_voice_design_qwen3,
)
from backend.app.domain.llm import MissingProviderCredential, OpenAICompatibleSegmentationClient
from backend.app.domain.novel import Chapter, ChapterWorkbench, ParagraphModule, parse_novel_text
from backend.app.domain.novel_files import NovelFileError, extract_novel_file
from backend.app.domain.providers import default_provider_registry
from backend.app.domain.roles import RoleCard, RoleCollection, default_role_cards
from backend.app.domain.segmentation import repair_json_output_once, validate_segmentation_result
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
CHAPTER_PARSER_SCRIPT_DIR = ROOT / "scripts/chapter_parsers"
REAL_VOICE_ROOT = Path(os.environ.get("NOVELVOICE_REAL_VOICE_ROOT", "/Users/gaojing/Downloads/真实测试样本/音频"))
DEFAULT_TTS_SCRIPT = ROOT / "backend/tts/qwen3_tts_server.py"
DEFAULT_BASE_MODEL_PATH = "/Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-Base"
DEFAULT_VOICE_DESIGN_MODEL_PATH = "/Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"


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
    app = FastAPI(title="NovelVoice-Agent v0.22 Harness API")
    OUTPUT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_VOICE_RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs/audio", StaticFiles(directory=OUTPUT_AUDIO_DIR), name="output_audio")
    voices = VoiceResourceCollection(default_voice_resources(REAL_VOICE_ROOT))
    app.state.workflow = {
        "chapters": [],
        "workbenches": {},
        "voices": voices,
        "roles": _seed_roles_from_voices(voices),
        "voice_jobs": {},
        "voice_previews": {},
        "tts_process": None,
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
        return {
            "chapter": _chapter_to_dict(chapter),
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
        provider = _segmentation_provider_from_config(app)
        try:
            raw_output = OpenAICompatibleSegmentationClient(
                provider=provider,
                api_key_lookup=_api_key_lookup_from_config(app),
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
        output_path = OUTPUT_AUDIO_DIR / f"{preview_id}.wav"
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
        )
        _state(app)["voice_previews"][preview_id] = resource
        return {
            "voice": _voice_to_dict(resource),
            "audio_url": f"/outputs/audio/{preview_id}.wav",
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
        base_url = str(config.get("base_url") or "").rstrip("/")
        if not base_url:
            raise HTTPException(status_code=400, detail="base_url is required")
        headers = {"Content-Type": "application/json"}
        api_key = str(config.get("api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(f"{base_url}/models", headers=headers, method="GET")
        try:
            await asyncio.to_thread(_test_models_endpoint, request)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"远端模型连接失败：{exc}") from exc
        return {"ok": True, "message": "远端模型连接成功"}

    @app.post("/api/model-config/tts/start")
    async def start_local_tts_service(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config = {**_state(app)["model_config"]["tts"], **((payload or {}).get("tts") or {})}
        model_path = str(config.get("model_path") or "").strip()
        if not model_path:
            raise HTTPException(status_code=400, detail="model_path is required")
        voice_design_model_path = str(config.get("voice_design_model_path") or "").strip()
        current = _state(app).get("tts_process")
        if current is not None and current.poll() is None:
            return {"ok": True, "message": "本地 TTS 服务已在运行", "pid": current.pid}

        python_bin = os.environ.get("QWEN3_TTS_PYTHON", sys.executable)
        base_url = str(config.get("base_url") or "http://127.0.0.1:7811")
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
        return {
            "ok": True,
            "message": "本地 TTS 服务启动成功，模型可能仍在加载",
            "pid": process.pid,
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
            duration_seconds = synthesize_local_qwen3(
                request,
                output_path=output_path,
                service_base_url=_state(app)["model_config"]["tts"].get("base_url"),
            )
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
    provider["base_url"] = config.get("base_url") or provider["base_url"]
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


def _start_tts_process(command: list[str]) -> subprocess.Popen:
    return subprocess.Popen(command, cwd=str(ROOT))


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
