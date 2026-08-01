from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import shutil
import sqlite3
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

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from backend.app.agents.registry import AgentRegistry
from backend.app.application.runtime_state import restore_runtime_state, save_runtime_state
from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill
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
from backend.app.domain.dubbing_workflow import (
    AiSegmentationService,
    DubbingWorkflow,
    LangChainRoleAnalysisSkill,
    RoleAnalysisCandidate,
    create_whole_paragraph_utterance_drafts,
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
from backend.app.repositories.sqlite import SQLiteRepository

ROOT = Path(__file__).resolve().parents[3]


def _service_env(name: str, default: str = "") -> str:
    """读取书弈 Agent 的统一运行时环境变量。"""
    return str(os.environ.get(name) or default)


DEFAULT_DATA_ROOT = Path(_service_env("SHUYI_DATA_DIR", str(ROOT / "data")))
OUTPUT_AUDIO_DIR = DEFAULT_DATA_ROOT / "outputs/audio"
OUTPUT_VOICE_RESOURCE_DIR = DEFAULT_DATA_ROOT / "blobs/voice-profiles"
OUTPUT_EXPORT_DIR = DEFAULT_DATA_ROOT / "outputs/exports"
CHAPTER_RULE_DIR = DEFAULT_DATA_ROOT / "cache/chapter-rules"
BUNDLED_CHAPTER_RULE_DIR = ROOT / "scripts/chapter_rules"
REAL_VOICE_ROOT = Path(_service_env("SHUYI_REAL_VOICE_ROOT", str(ROOT / "assets/samples/voices")))
DEFAULT_TTS_SCRIPT = ROOT / "backend/tts/qwen3_tts_server.py"
DEFAULT_BASE_MODEL_PATH = str(ROOT / "models/Qwen3-TTS-12Hz-1.7B-Base")
DEFAULT_VOICE_DESIGN_MODEL_PATH = str(ROOT / "models/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
DEFAULT_TTS_STARTUP_TIMEOUT_SECONDS = 300.0
SERVICE_NAME = "shuyi-agent"
SERVICE_VERSION = "0.4.2"
MAX_NOVEL_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_REFERENCE_AUDIO_BYTES = 25 * 1024 * 1024


def _chapter_to_dict(chapter: Chapter) -> dict[str, Any]:
    return asdict(chapter)


def _paragraph_to_dict(paragraph) -> dict[str, Any]:
    return asdict(paragraph)


def _state(app: FastAPI) -> dict[str, Any]:
    return app.state.workflow


def _voice_to_dict(voice: VoiceResource) -> dict[str, Any]:
    return voice.to_dict()


async def _read_limited_upload(file: UploadFile, *, max_bytes: int) -> bytes:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="上传文件超过大小限制")
    return data


def _public_voice_to_dict(voice: VoiceResource) -> dict[str, Any]:
    payload = voice.to_dict()
    audio_url = f"/api/v1/voice-profiles/{voice.voice_id}/audio"
    payload["reference_audio_path"] = audio_url
    payload["playable_audio_path"] = audio_url
    return payload


def _public_role_to_dict(role: RoleCard) -> dict[str, Any]:
    payload = role.to_dict()
    if role.voice_resource_id:
        audio_url = f"/api/v1/voice-profiles/{role.voice_resource_id}/audio"
        payload["reference_audio_path"] = audio_url
        payload["playable_voice_path"] = audio_url
    else:
        payload["reference_audio_path"] = None
        payload["playable_voice_path"] = None
    return payload


def _resolve_audio_path(path_text: str) -> Path:
    download_prefix = "/api/v1/downloads/voice-profiles/"
    if path_text.startswith(download_prefix):
        target = (OUTPUT_VOICE_RESOURCE_DIR / path_text.removeprefix(download_prefix)).resolve()
        if _is_inside(target, OUTPUT_VOICE_RESOURCE_DIR):
            return target
    voice_prefix = "/api/v1/voice-profiles/"
    if path_text.startswith(voice_prefix) and path_text.endswith("/audio"):
        voice_id = path_text.removeprefix(voice_prefix).removesuffix("/audio").strip("/")
        matches = sorted(
            OUTPUT_VOICE_RESOURCE_DIR.glob(f"{_safe_audio_filename(voice_id).rsplit('.', 1)[0]}.*")
        )
        if matches:
            return matches[0]
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def _is_inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _is_allowed_audio_path(path: Path) -> bool:
    allowed_roots = (
        REAL_VOICE_ROOT,
        OUTPUT_VOICE_RESOURCE_DIR.parent,
        OUTPUT_AUDIO_DIR.parent,
    )
    return any(_is_inside(path, root) for root in allowed_roots)


def _store_voice_resource_audio(path_text: str, *, voice_id: str) -> str:
    source = _resolve_audio_path(path_text)
    if not source.is_file() or not _is_allowed_audio_path(source):
        raise HTTPException(status_code=400, detail="参考音频必须来自受控的音频目录")
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
    text_model = providers["openai-compatible-text"]
    return {
        "text_model": {
            "base_url": os.environ.get("SHUYI_TEXT_MODEL_BASE_URL", text_model["base_url"]),
            "model": os.environ.get("SHUYI_TEXT_MODEL_NAME", text_model["model"]),
        },
        "tts": {
            "base_url": os.environ.get("QWEN3_TTS_BASE_URL", "http://127.0.0.1:7811"),
            "model_path": os.environ.get("QWEN3_TTS_MODEL_PATH", DEFAULT_BASE_MODEL_PATH),
            "voice_design_model_path": os.environ.get(
                "QWEN3_TTS_VOICE_DESIGN_MODEL_PATH",
                DEFAULT_VOICE_DESIGN_MODEL_PATH,
            ),
        },
    }


def _normalize_model_config(config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _default_model_config()
    if not isinstance(config, dict):
        return normalized

    legacy_text_model = (
        config.get("text_model")
        or config.get("chapter_agent")
        or config.get("llm")
        or {}
    )
    if isinstance(legacy_text_model, dict):
        normalized["text_model"].update(
            {
                key: value
                for key, value in legacy_text_model.items()
                if key in {"base_url", "model"}
            }
        )
    if isinstance(config.get("tts"), dict):
        normalized["tts"].update(
            {
                key: value
                for key, value in config["tts"].items()
                if key in {"base_url", "model_path", "voice_design_model_path"}
            }
        )
    return normalized


def _has_text_model_api_key(app: FastAPI) -> bool:
    in_memory = str(getattr(app.state, "text_model_api_key", "") or "").strip()
    environment_value = str(
        os.environ.get("SHUYI_TEXT_MODEL_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    ).strip()
    return bool(in_memory or environment_value)


def _redacted_model_config(
    config: dict[str, Any],
    *,
    has_text_model_api_key: bool = False,
) -> dict[str, Any]:
    normalized = _normalize_model_config(config)
    return {
        "text_model": {
            **normalized["text_model"],
            "has_api_key": has_text_model_api_key,
        },
        "tts": dict(normalized["tts"]),
    }


def _prune_expired_secret_exchanges(app: FastAPI) -> None:
    now = time.monotonic()
    exchanges = getattr(app.state, "secret_exchanges", {})
    for secret_id, item in list(exchanges.items()):
        if item["expires_at"] <= now:
            exchanges.pop(secret_id, None)


def _create_secret_exchange(app: FastAPI, byte_length: int) -> dict[str, str]:
    _prune_expired_secret_exchanges(app)
    safe_length = max(16, min(4096, int(byte_length or 256)))
    secret_id = secrets.token_urlsafe(24)
    pad = secrets.token_bytes(safe_length)
    app.state.secret_exchanges[secret_id] = {
        "pad": pad,
        "expires_at": time.monotonic() + 120,
    }
    return {
        "secret_id": secret_id,
        "pad_b64": base64.b64encode(pad).decode("ascii"),
        "expires_in_seconds": 120,
    }


def _consume_secret_exchange(app: FastAPI, payload: Any) -> str:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="缺少密钥交换数据")
    _prune_expired_secret_exchanges(app)
    secret_id = str(payload.get("secret_id") or "")
    exchange = app.state.secret_exchanges.pop(secret_id, None)
    if not exchange:
        raise HTTPException(status_code=400, detail="密钥交换已过期，请重新输入")
    try:
        ciphertext = base64.b64decode(str(payload.get("ciphertext_b64") or ""), validate=True)
        expected_length = int(payload.get("length") or len(ciphertext))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="密钥交换数据无效") from None
    pad = exchange["pad"]
    if expected_length < 0 or expected_length > len(ciphertext) or expected_length > len(pad):
        raise HTTPException(status_code=400, detail="密钥交换长度无效")
    secret_bytes = bytes(
        ciphertext[index] ^ pad[index] for index in range(expected_length)
    )
    try:
        return secret_bytes.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="密钥交换内容无法解码") from None


def _set_text_model_api_key_from_exchange(app: FastAPI, payload: Any) -> None:
    secret = _consume_secret_exchange(app, payload)
    if not secret:
        raise HTTPException(status_code=400, detail="文本模型 API Key 不能为空")
    app.state.text_model_api_key = secret


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
    app = FastAPI(
        title="书弈 Agent API",
        description="基于 Agent 的多人有声书自动配音工作台后端接口",
        version=SERVICE_VERSION,
    )
    api_token = _service_env("SHUYI_API_TOKEN").strip()
    allowed_origins = [
        origin.strip() for origin in _service_env("SHUYI_CORS_ORIGINS").split(",") if origin.strip()
    ]
    data_root_value = _service_env("SHUYI_DATA_DIR").strip()
    data_root = Path(data_root_value).expanduser() if data_root_value else None
    repository = SQLiteRepository(data_root / "shuyi-agent.sqlite3" if data_root else ":memory:")
    repository.initialize()
    app.state.repository = repository
    app.state.agent_registry = AgentRegistry.default()
    app.state.chapter_rule_dir = (
        data_root / "cache/chapter-rules" if data_root else CHAPTER_RULE_DIR
    )
    app.state.startup_ready = True
    app.state.require_tts_ready = _service_env("SHUYI_REQUIRE_TTS_READY", "0") == "1"
    app.state.secret_exchanges = {}
    app.state.text_model_api_key = ""

    @app.middleware("http")
    async def versioned_api_boundary(request: Request, call_next):
        path = str(request.scope.get("path") or "")
        if request.method == "OPTIONS":
            return await call_next(request)
        if path.startswith("/api/") and not path.startswith("/api/v1/"):
            return JSONResponse(status_code=404, content={"detail": "接口不存在"})
        if path.startswith("/api/v1/"):
            authorization = request.headers.get("Authorization", "")
            provided_token = authorization.removeprefix("Bearer ").strip()
            if not authorization.startswith("Bearer ") or not api_token:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "需要访问令牌"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not secrets.compare_digest(provided_token, api_token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "访问令牌无效"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        response = await call_next(request)
        if request.method in {"POST", "PATCH", "PUT", "DELETE"} and response.status_code < 400:
            try:
                save_runtime_state(repository, _state(app))
            except (OSError, RuntimeError, TypeError, ValueError):
                app.state.startup_ready = False
        return response

    # CORS 必须包在鉴权中间件外层，确保浏览器能读取 401/403 的中文错误。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )

    async def require_bearer(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="需要访问令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        provided_token = authorization.removeprefix("Bearer ").strip()
        if not api_token or not secrets.compare_digest(provided_token, api_token):
            raise HTTPException(
                status_code=401,
                detail="访问令牌无效",
                headers={"WWW-Authenticate": "Bearer"},
            )

    OUTPUT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_VOICE_RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    voices = VoiceResourceCollection(
        _materialize_voice_resources(default_voice_resources(REAL_VOICE_ROOT))
    )
    app.state.workflow = {
        "chapters": [],
        "workbenches": {},
        "voices": voices,
        "roles": _seed_roles_from_voices(voices),
        "voice_jobs": {},
        "voice_previews": {},
        "tts_process": None,
        "model_config": _default_model_config(),
        "dubbing_workflows": {},
        "agent_streams": {},
    }
    restore_runtime_state(app.state.workflow, repository.get_workflow("application"))
    _state(app)["model_config"] = _normalize_model_config(_state(app).get("model_config"))

    @app.get("/health/live")
    async def liveness_probe() -> dict[str, str]:
        return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}

    @app.get("/health/startup")
    async def startup_probe():
        if not app.state.startup_ready:
            return JSONResponse(
                status_code=503,
                content={"status": "starting", "service": SERVICE_NAME, "version": SERVICE_VERSION},
            )
        return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}

    @app.get("/health/ready")
    async def readiness_probe():
        try:
            database_ready = repository.ping()
        except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError):
            database_ready = False
        tts_health = (
            _fetch_tts_health(_state(app)["model_config"]["tts"]["base_url"])
            if app.state.require_tts_ready
            else {"ready": False}
        )
        tts_ready = bool(tts_health.get("ready"))
        ready = database_ready and (tts_ready or not app.state.require_tts_ready)
        payload = {
            "status": "ok" if ready else "not_ready",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "database": "ready" if database_ready else "not_ready",
            "tts": "ready" if tts_ready else "not_ready",
        }
        return payload if ready else JSONResponse(status_code=503, content=payload)

    def role_payload() -> dict[str, Any]:
        collection = _state(app)["roles"]
        return {
            "roles": [_public_role_to_dict(role) for role in collection.list()],
            "role_options": collection.utterance_role_options(),
        }

    @app.get("/api/v1/characters", dependencies=[Depends(require_bearer)])
    async def list_v1_characters() -> dict[str, Any]:
        return role_payload()

    @app.get("/api/v1/model-config", dependencies=[Depends(require_bearer)])
    async def get_v1_model_config() -> dict[str, Any]:
        return {
            "config": _redacted_model_config(
                _state(app)["model_config"],
                has_text_model_api_key=_has_text_model_api_key(app),
            )
        }

    @app.get("/api/v1/downloads/{category}/{filename:path}", dependencies=[Depends(require_bearer)])
    async def download_generated_file(category: str, filename: str):
        directories = {
            "audio": OUTPUT_AUDIO_DIR,
            "voice-profiles": OUTPUT_VOICE_RESOURCE_DIR,
            "exports": OUTPUT_EXPORT_DIR,
        }
        directory = directories.get(category)
        if directory is None:
            raise HTTPException(status_code=404, detail="下载资源不存在")
        target = (directory / filename).resolve()
        if not _is_inside(target, directory) or not target.is_file():
            raise HTTPException(status_code=404, detail="下载资源不存在")
        return FileResponse(target, filename=target.name)

    @app.post("/api/v1/books/parse")
    async def parse_novel(payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(status_code=400, detail="文本内容不能为空")
        chapters = parse_novel_text(text)
        state = _state(app)
        state["chapters"] = chapters
        state["workbenches"] = {
            chapter.chapter_id: ChapterWorkbench.from_chapter(chapter) for chapter in chapters
        }
        return {"chapters": [_chapter_to_dict(chapter) for chapter in chapters]}

    @app.post("/api/v1/books/agent-chapter-split")
    async def ai_chapter_split(payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(status_code=400, detail="文本内容不能为空")
        return await _run_ai_chapter_split(app, text)

    @app.post("/api/v1/books/agent-chapter-split-file")
    async def ai_chapter_split_file(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        filename = str(file.filename or "").strip()
        if not filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        try:
            data = await _read_limited_upload(file, max_bytes=MAX_NOVEL_UPLOAD_BYTES)
            extracted = extract_novel_file(filename=filename, data=data)
        except (ValueError, NovelFileError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response = await _run_ai_chapter_split(app, extracted.text)
        response["source"] = {"filename": filename, "kind": extracted.kind}
        return response

    @app.get("/api/v1/chapters")
    async def list_chapters() -> dict[str, Any]:
        return {"chapters": [_chapter_to_dict(chapter) for chapter in _state(app)["chapters"]]}

    @app.get("/api/v1/chapters/{chapter_id}")
    async def get_chapter(chapter_id: str) -> dict[str, Any]:
        state = _state(app)
        workbench = state["workbenches"].get(chapter_id)
        if workbench is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        return {
            "chapter": _chapter_to_dict(workbench.chapter),
            "paragraphs": [
                _paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs
            ],
            "can_segment": workbench.can_segment,
        }

    @app.put("/api/v1/chapters/{chapter_id}/paragraphs")
    async def sync_chapter_paragraphs(chapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raw_paragraphs = payload.get("paragraphs")
        if not isinstance(raw_paragraphs, list):
            raise HTTPException(status_code=400, detail="段落列表不能为空")
        paragraphs = [
            _paragraph_from_payload(item, index)
            for index, item in enumerate(raw_paragraphs, start=1)
        ]
        visible = [
            paragraph
            for paragraph in paragraphs
            if not paragraph.deleted and paragraph.text.strip()
        ]
        if not visible:
            raise HTTPException(status_code=400, detail="至少需要一段可见正文")

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
            "paragraphs": [
                _paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs
            ],
            "can_segment": workbench.can_segment,
        }
        if payload.get("confirm") is True:
            response["utterance_drafts"] = create_whole_paragraph_utterance_drafts(
                workbench.visible_paragraphs
            )
        return response

    @app.post("/api/v1/chapters/{chapter_id}/agent-runs")
    async def start_agent_run(
        chapter_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        state = _state(app)
        workbench = state["workbenches"].get(chapter_id)
        if workbench is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        workflow = _create_dubbing_workflow(app)
        try:
            result = workflow.start_role_analysis(
                chapter_id=chapter_id,
                chapter_title=workbench.chapter.title,
                paragraphs=[
                    _paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs
                ],
                existing_roles=[role.to_dict() for role in state["roles"].list()],
            )
        except MissingProviderCredential as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"角色分析 Agent 失败：{exc}") from exc
        state["dubbing_workflows"][result.thread_id] = workflow
        repository.save_agent_run(
            run_id=result.thread_id,
            agent_id="role_analyzer",
            status=result.status,
            checkpoint={
                "chapter_id": chapter_id,
                "role_candidate_count": len(result.role_candidates),
            },
        )
        return result.to_dict()

    @app.post("/api/v1/agent-runs/{thread_id}/dubbing-arrangement")
    async def complete_dubbing_arrangement(
        thread_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        workflow = _dubbing_workflow(app, thread_id)
        roles = _roles_for_dubbing_payload(app, payload or {})
        try:
            result = workflow.resume_after_roles(
                thread_id=thread_id,
                roles=roles,
                existing_utterances_by_paragraph=_utterances_by_paragraph_from_payload(
                    payload or {}
                ),
            )
        except MissingProviderCredential as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"配音编排 Agent 失败：{exc}") from exc
        status_code = 422 if result.status == "failed" else 200
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=result.to_dict())
        return result.to_dict()

    @app.post("/api/v1/agent-runs/{thread_id}/events")
    async def stream_agent_run_events(
        thread_id: str,
        request: Request,
        payload: dict[str, Any] | None = None,
    ):
        roles = _roles_for_dubbing_payload(app, payload or {})
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload or {})
        streams = _state(app)["agent_streams"]
        persisted_events = repository.list_events(thread_id)
        persisted_terminal = any(
            event["event"] in {"completed", "failed"} for event in persisted_events
        )
        stream_state = streams.setdefault(
            thread_id,
            {
                "events": persisted_events,
                "started": persisted_terminal,
                "terminal": persisted_terminal,
                "lock": threading.Lock(),
            },
        )

        def emit(event_name: str, data: dict[str, Any]) -> None:
            with stream_state["lock"]:
                sequence = max((event["id"] for event in stream_state["events"]), default=0) + 1
                event = {"id": sequence, "event": event_name, "data": data}
            try:
                repository.append_event(
                    run_id=thread_id,
                    sequence=sequence,
                    event_type=event_name,
                    payload=data,
                )
            except Exception as exc:
                with stream_state["lock"]:
                    stream_state["events"].append(
                        {
                            "id": sequence,
                            "event": "failed",
                            "data": {"message": f"Agent 事件持久化失败：{exc}"},
                        }
                    )
                    stream_state["terminal"] = True
                raise RuntimeError("Agent 事件持久化失败") from exc
            with stream_state["lock"]:
                stream_state["events"].append(event)
                if event_name in {"completed", "failed"}:
                    stream_state["terminal"] = True

        with stream_state["lock"]:
            should_start = not stream_state["started"] and not stream_state["terminal"]
            if should_start:
                stream_state["started"] = True

        if should_start:
            workflow = _dubbing_workflow(app, thread_id)

            def run_workflow() -> None:
                try:
                    result = workflow.resume_after_roles(
                        thread_id=thread_id,
                        roles=roles,
                        existing_utterances_by_paragraph=utterances_by_paragraph,
                        on_role_selected=lambda event: emit("role_selected", event),
                    )
                    event_name = "failed" if result.status == "failed" else "completed"
                    emit(event_name, result.to_dict())
                    repository.save_agent_run(
                        run_id=thread_id,
                        agent_id="dubbing_director",
                        status=result.status,
                        checkpoint={
                            "chapter_id": repository.get_agent_run(thread_id)["checkpoint"][
                                "chapter_id"
                            ],
                            "event_count": len(stream_state["events"]),
                        },
                    )
                except Exception as exc:  # noqa: BLE001 - 后台任务必须始终写入终止事件。
                    with stream_state["lock"]:
                        terminal = bool(stream_state["terminal"])
                    if not terminal:
                        emit("failed", {"message": str(exc)})

            threading.Thread(target=run_workflow, daemon=True).start()

        try:
            last_event_id = max(0, int(request.headers.get("Last-Event-ID", "0")))
        except ValueError:
            last_event_id = 0

        async def stream_events():
            cursor = last_event_id
            while True:
                pending = repository.list_events(thread_id, after_sequence=cursor)
                with stream_state["lock"]:
                    terminal = bool(stream_state["terminal"])
                for item in pending:
                    cursor = item["id"]
                    data = json.dumps(item["data"], ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {item['id']}\nevent: {item['event']}\ndata: {data}\n\n"
                terminal = terminal or any(
                    item["event"] in {"completed", "failed"} for item in pending
                )
                if terminal and not pending:
                    break
                await asyncio.sleep(0.05)

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.patch("/api/v1/paragraphs/{paragraph_id}")
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
            "paragraphs": [
                _paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs
            ],
            "can_segment": workbench.can_segment,
        }

    @app.post("/api/v1/paragraphs/{paragraph_id}/segment")
    async def segment_paragraph(paragraph_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        workbench = _find_workbench_for_paragraph(app, paragraph_id)
        if not workbench.can_segment:
            raise HTTPException(status_code=409, detail="开始配音片段划分前必须先确认段落")
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
            raise HTTPException(status_code=502, detail="配音编排 Agent 的台词划分失败") from exc
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

    async def roles(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        collection = _state(app)["roles"]
        if payload:
            collection.upsert(_role_payload_with_resource(app, payload))
        return {
            "roles": [_public_role_to_dict(role) for role in collection.list()],
            "role_options": collection.utterance_role_options(),
        }

    async def update_role(role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        collection = _state(app)["roles"]
        current = collection.get(role_id)
        updates = _role_payload_with_resource(app, {**payload, "role_id": role_id})
        updated = current.with_updates(**updates)
        collection.upsert(updated)
        return {
            "role": _public_role_to_dict(updated),
            "role_options": collection.utterance_role_options(),
        }

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
            "roles": [_public_role_to_dict(role) for role in collection.list()],
            "role_options": collection.utterance_role_options(),
            "utterances_by_paragraph": utterances_by_paragraph,
        }
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=response)
        return response

    app.add_api_route("/api/v1/characters", roles, methods=["POST"])
    app.add_api_route("/api/v1/characters/{role_id}", update_role, methods=["PATCH"])
    app.add_api_route("/api/v1/characters/{role_id}", delete_role, methods=["DELETE"])

    @app.get("/api/v1/voice-profiles")
    async def list_voice_resources() -> dict[str, Any]:
        voices = _state(app)["voices"]
        return {"voices": [_public_voice_to_dict(voice) for voice in voices.list()]}

    @app.post("/api/v1/voice-profiles")
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
        return {
            "voice": _public_voice_to_dict(resource),
            "voices": [_public_voice_to_dict(voice) for voice in voices.list()],
        }

    @app.post("/api/v1/voice-profiles/reference-audio")
    async def upload_reference_audio(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        filename = _safe_audio_filename(str(file.filename or "参考音频.wav"))
        try:
            audio_bytes = await _read_limited_upload(file, max_bytes=MAX_REFERENCE_AUDIO_BYTES)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="参考音频读取失败") from exc
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="参考音频文件不能为空")
        target = OUTPUT_VOICE_RESOURCE_DIR / filename
        if target.exists():
            target = (
                OUTPUT_VOICE_RESOURCE_DIR
                / f"{target.stem}-{len(list(OUTPUT_VOICE_RESOURCE_DIR.glob(target.stem + '*'))) + 1}{target.suffix}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio_bytes)
        return {
            "filename": filename,
            "reference_audio_path": f"/api/v1/downloads/voice-profiles/{target.name}",
        }

    @app.post("/api/v1/voice-profiles/generate")
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
            generation_note = "已生成试听音色。"
            model_requirement = None
        except TTSServiceError as exc:
            duration_seconds = _write_substitute_wav(output_path)
            generation_status = "substitute"
            generation_note = "已生成本地预览音频。"
            model_requirement = None
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
            "voice": _public_voice_to_dict(resource),
            "audio_url": f"/api/v1/downloads/voice-profiles/{preview_id}.wav",
            "duration_seconds": duration_seconds,
            "generation_status": generation_status,
            "generation_note": generation_note,
            "model_requirement": model_requirement,
        }

    @app.patch("/api/v1/voice-profiles/{voice_id}")
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
        return {
            "voice": _public_voice_to_dict(updated),
            "voices": [_public_voice_to_dict(voice) for voice in voices.list()],
        }

    @app.get(
        "/api/v1/voice-profiles/{voice_id}/audio",
        dependencies=[Depends(require_bearer)],
    )
    async def get_voice_resource_audio(voice_id: str):
        try:
            voice = _state(app)["voices"].get(voice_id)
        except KeyError:
            voice = _state(app)["voice_previews"].get(voice_id)
            if voice is None:
                raise HTTPException(status_code=404, detail="参考音频不存在") from None
        audio_path = Path(voice.reference_audio_path)
        if not audio_path.is_absolute():
            audio_path = ROOT / audio_path
        if not audio_path.is_file() or not _is_allowed_audio_path(audio_path):
            raise HTTPException(status_code=404, detail="参考音频不存在")
        return FileResponse(audio_path)

    @app.delete("/api/v1/voice-profiles/{voice_id}")
    async def delete_voice_resource(voice_id: str) -> dict[str, Any]:
        voices = _state(app)["voices"]
        voices.remove(voice_id)
        return {"voices": [_public_voice_to_dict(voice) for voice in voices.list()]}

    @app.get("/api/v1/model-config")
    async def get_model_config() -> dict[str, Any]:
        return {
            "config": _redacted_model_config(
                _state(app)["model_config"],
                has_text_model_api_key=_has_text_model_api_key(app),
            )
        }

    @app.post("/api/v1/model-config/secret-exchange")
    async def create_model_config_secret_exchange(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        byte_length = int((payload or {}).get("byte_length") or 256)
        return _create_secret_exchange(app, byte_length)

    @app.patch("/api/v1/model-config")
    async def update_model_config(payload: dict[str, Any]) -> dict[str, Any]:
        config = _normalize_model_config(_state(app)["model_config"])
        if isinstance(payload.get("text_model"), dict):
            text_model_updates = {
                key: value
                for key, value in payload["text_model"].items()
                if key in {"base_url", "model"}
            }
            config["text_model"] = {**config["text_model"], **text_model_updates}
        if payload.get("text_model_secret"):
            _set_text_model_api_key_from_exchange(app, payload["text_model_secret"])
        if isinstance(payload.get("tts"), dict):
            tts_updates = {
                key: value
                for key, value in payload["tts"].items()
                if key in {"base_url", "model_path", "voice_design_model_path"}
            }
            config["tts"] = {**config["tts"], **tts_updates}
        _state(app)["model_config"] = config
        return {
            "config": _redacted_model_config(
                config,
                has_text_model_api_key=_has_text_model_api_key(app),
            )
        }

    @app.post("/api/v1/model-config/text-model/test")
    async def test_text_model_link(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if payload.get("text_model_secret"):
            _set_text_model_api_key_from_exchange(app, payload["text_model_secret"])
        supplied = payload.get("text_model") or {}
        config = {
            **_state(app)["model_config"]["text_model"],
            **{key: value for key, value in supplied.items() if key in {"base_url", "model"}},
            "api_key": _api_key_lookup_from_config(app)("SHUYI_TEXT_MODEL_API_KEY"),
        }
        try:
            await _test_model_link(config)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"文本模型连接失败：{exc}") from exc
        return {"ok": True, "message": "文本模型连接成功"}

    @app.post("/api/v1/model-config/tts/test")
    async def test_tts_model_connection(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        supplied_tts = (payload or {}).get("tts") or {}
        tts_updates = {
            key: value
            for key, value in supplied_tts.items()
            if key in {"base_url", "model_path", "voice_design_model_path"}
        }
        config = {**_state(app)["model_config"]["tts"], **tts_updates}
        _state(app)["model_config"]["tts"] = config
        base_url = str(config.get("base_url") or "http://127.0.0.1:7811")
        health = await asyncio.to_thread(_fetch_tts_health, base_url)
        if not _is_tts_ready(health):
            raise HTTPException(status_code=503, detail=_format_tts_not_ready_message(health))
        return {
            "ok": True,
            "message": "TTS模型连接成功，VoiceDesign 已就绪",
            "health": health,
            "progress": 100,
        }

    @app.post("/api/v1/model-config/tts/start")
    async def start_local_tts_service(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        supplied_tts = (payload or {}).get("tts") or {}
        tts_updates = {
            key: value
            for key, value in supplied_tts.items()
            if key in {"base_url", "model_path", "voice_design_model_path"}
        }
        config = {**_state(app)["model_config"]["tts"], **tts_updates}
        model_path = str(config.get("model_path") or "").strip()
        if not model_path:
            raise HTTPException(status_code=400, detail="必须配置 TTS 模型路径")
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

    @app.post("/api/v1/dubbing-segments/{utterance_id}/dubbing-jobs")
    async def synthesize_speech(utterance_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        role_id = payload.get("role_id")
        if not role_id:
            raise HTTPException(status_code=400, detail="角色编号不能为空")
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
                "audio_url": f"/api/v1/downloads/audio/{job_id}.wav",
                "duration_seconds": duration_seconds,
                "warning": "本地 TTS 服务不可用，已返回可重复生成的占位 WAV。",
            }

        _state(app)["voice_jobs"][job_id] = job
        return {
            "voice_job": job.to_dict(),
            "audio_url": f"/api/v1/downloads/audio/{job_id}.wav",
            "duration_seconds": duration_seconds,
        }

    @app.post("/api/v1/dubbing-jobs/{chapter_id}")
    async def synthesize_chapter_speech_batch(
        chapter_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        roles = _roles_for_dubbing_payload(app, payload or {})
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
        payload = report.to_dict()
        for utterances in payload["utterances_by_paragraph"].values():
            for utterance in utterances:
                audio_path = str(utterance.get("audio_path") or "")
                if audio_path:
                    filename = Path(audio_path).name
                    utterance["audio_path"] = f"outputs/audio/{filename}"
                    utterance["audio_url"] = f"/api/v1/downloads/audio/{filename}"
        return payload

    @app.post("/api/v1/exports/{chapter_id}")
    async def export_chapter_audio_endpoint(
        chapter_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        roles = _roles_for_dubbing_payload(app, payload or {})
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload or {})
        chapter_title = str((payload or {}).get("chapter_title") or chapter_id)
        pause_ms = int((payload or {}).get("pause_ms") or 300)
        speed = float((payload or {}).get("speed") or 1.0)
        export_dir = (
            OUTPUT_EXPORT_DIR
            / f"{_safe_audio_filename(chapter_id).removesuffix('.wav')}-{int(time.time())}"
        )
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
        archive_path = Path(
            await asyncio.to_thread(shutil.make_archive, str(export_dir), "zip", export_dir)
        )
        return {
            "status": report.status,
            "item_count": report.item_count,
            "missing_count": report.missing_count,
            "message": report.message,
            "download_url": f"/api/v1/downloads/exports/{archive_path.name}",
        }

    return app


async def _run_ai_chapter_split(app: FastAPI, text: str) -> dict[str, Any]:
    provider = _chapter_agent_provider_from_config(app)
    skill = ChapterSplitSkill(
        provider=provider,
        api_key_lookup=_chapter_agent_api_key_lookup_from_config(app),
        system_prompt=app.state.agent_registry.get("novel_parser").prompt_text,
    )
    agent = AiChapterSplitAgent(
        rules_dir=app.state.chapter_rule_dir,
        bundled_rules_dir=BUNDLED_CHAPTER_RULE_DIR,
        skill=skill,
    )
    try:
        result = await asyncio.to_thread(agent.split, text)
    except MissingProviderCredential as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="文本模型执行失败") from exc
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
            "rule_path": str(result.rule_path) if result.rule_path else None,
            "trace": result.trace,
            "validation_errors": result.validation.errors,
        },
    }


def _create_dubbing_workflow(app: FastAPI) -> DubbingWorkflow:
    role_provider = _chapter_agent_provider_from_config(app)
    segmentation_provider = _segmentation_provider_from_config(app)
    return DubbingWorkflow(
        role_skill=LangChainRoleAnalysisSkill(
            provider=role_provider,
            api_key_lookup=_chapter_agent_api_key_lookup_from_config(app),
            role_analysis_system_prompt=app.state.agent_registry.get("role_analyzer").prompt_text,
            dubbing_system_prompt=app.state.agent_registry.get("dubbing_director").prompt_text,
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


def _dubbing_workflow(app: FastAPI, thread_id: str) -> DubbingWorkflow:
    workflow = _state(app)["dubbing_workflows"].get(thread_id)
    if workflow is not None:
        return workflow
    run = app.state.repository.get_agent_run(thread_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent 运行记录不存在")
    chapter_id = str(run["checkpoint"].get("chapter_id") or "")
    workbench = _state(app)["workbenches"].get(chapter_id)
    if workbench is None:
        raise HTTPException(status_code=409, detail="Agent 运行对应的章节资源无法恢复")
    workflow = _create_dubbing_workflow(app)
    workflow.restore_waiting_session(
        thread_id=thread_id,
        chapter_id=chapter_id,
        chapter_title=workbench.chapter.title,
        paragraphs=[_paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs],
        existing_roles=[role.to_dict() for role in _state(app)["roles"].list()],
    )
    _state(app)["dubbing_workflows"][thread_id] = workflow
    return workflow


def _roles_for_dubbing_payload(app: FastAPI, payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_roles = payload.get("roles")
    collection = _state(app)["roles"]
    if isinstance(raw_roles, list):
        for raw_role in raw_roles:
            if isinstance(raw_role, dict) and raw_role.get("role_id"):
                collection.upsert(_role_payload_with_resource(app, raw_role))
    return [role.to_dict() for role in collection.list()]


def _utterances_by_paragraph_from_payload(
    payload: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    raw = payload.get("utterances_by_paragraph")
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, list[dict[str, Any]]] = {}
    for paragraph_id, utterances in raw.items():
        if not isinstance(utterances, list):
            continue
        normalized[str(paragraph_id)] = [
            dict(item) for item in utterances if isinstance(item, dict)
        ]
    return normalized


def _write_substitute_wav(
    path: Path, *, duration_seconds: float = 0.75, sample_rate: int = 16000
) -> float:
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
    raise HTTPException(status_code=404, detail="段落不存在")


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{field} 不能为空")
    return value.strip()


def _paragraph_from_payload(payload: Any, index: int) -> ParagraphModule:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="段落条目必须是对象")
    text = str(payload.get("text") or "").strip()
    return ParagraphModule(
        paragraph_id=str(payload.get("paragraph_id") or f"p-{index:04d}"),
        text=text,
        collapsed=bool(payload.get("collapsed", False)),
        deleted=bool(payload.get("deleted", False)),
        confirmed=bool(payload.get("confirmed", False)),
    )


def _segmentation_provider_from_config(app: FastAPI) -> dict[str, Any]:
    return _text_model_provider_from_config(app)


def _text_model_provider_from_config(app: FastAPI) -> dict[str, Any]:
    provider = default_provider_registry()["openai-compatible-text"]
    config = _normalize_model_config(_state(app)["model_config"])["text_model"]
    provider["base_url"] = config.get("base_url") or provider["base_url"]
    provider["model"] = config.get("model") or provider["model"]
    return provider


def _api_key_lookup_from_config(app: FastAPI):
    def lookup(name: str) -> str | None:
        if name == "SHUYI_TEXT_MODEL_API_KEY":
            return (
                str(getattr(app.state, "text_model_api_key", "") or "").strip()
                or os.environ.get("SHUYI_TEXT_MODEL_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
            )
        return os.environ.get(name)

    return lookup


def _chapter_agent_provider_from_config(app: FastAPI) -> dict[str, Any]:
    return _text_model_provider_from_config(app)


def _chapter_agent_api_key_lookup_from_config(app: FastAPI):
    return _api_key_lookup_from_config(app)


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


async def _test_model_link(config: dict[str, Any]) -> None:
    base_url = str(config.get("base_url") or "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="服务地址不能为空")
    headers = {"Content-Type": "application/json"}
    api_key = str(config.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(f"{base_url}/models", headers=headers, method="GET")
    await asyncio.to_thread(_test_models_endpoint, request)


def _start_tts_process(command: list[str]) -> subprocess.Popen:
    return subprocess.Popen(command, cwd=str(ROOT))


def _tts_startup_timeout_seconds() -> float:
    raw_value = os.environ.get("SHUYI_TTS_STARTUP_TIMEOUT_SECONDS", "")
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
        f"最近一次健康检查错误：{health.get('error', '未知错误')}"
    )


def _wait_for_tts_ready(
    process: subprocess.Popen | None,
    base_url: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    timeout = _tts_startup_timeout_seconds() if timeout_seconds is None else timeout_seconds
    deadline = time.monotonic() + timeout
    last_health: dict[str, Any] = {"reachable": False, "error": "尚未执行健康检查"}
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
        raise HTTPException(status_code=400, detail="音色档案不存在") from exc
    return _role_with_voice(role, voice)


app = create_app()
