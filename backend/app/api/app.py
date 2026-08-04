from __future__ import annotations

import asyncio
import base64
import hashlib
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
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from backend.app.agents.registry import AgentRegistry
from backend.app.application.runtime_state import restore_runtime_state, save_runtime_state
from backend.app.domain.agent_memory import (
    build_long_term_memory_fact,
    build_run_memory_snapshot,
    build_story_memory_context,
)
from backend.app.domain.agent_trace import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_RESERVED_OUTPUT_TOKENS,
    build_token_context_report,
    summarize_for_trace,
)
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
from backend.app.domain.long_text_splitter import (
    bulk_update_role,
    detect_long_utterances,
    merge_utterance_groups,
    prepare_retry_queue,
    split_long_utterance_groups,
    split_text_for_tts,
    text_conservation_report,
)
from backend.app.domain.novel import Chapter, ChapterWorkbench, ParagraphModule, parse_novel_text
from backend.app.domain.novel_files import NovelFileError, extract_novel_file
from backend.app.domain.production_planner import (
    PLANNER_AGENT_ID,
    build_production_planner_run,
    execute_planner_run,
    planner_run_from_payload,
    planner_run_to_memory_payload,
    review_planner_run,
)
from backend.app.domain.project_workspace import (
    DEFAULT_PROJECT_ID,
    build_quality_report,
    build_review_queue,
    default_project,
    project_from_payload,
    safe_project_id,
    with_output_roots,
)
from backend.app.domain.providers import default_provider_registry
from backend.app.domain.roles import RoleCard, RoleCollection, default_role_cards
from backend.app.domain.story_memory import (
    DEFAULT_EMBEDDING_API_KEY_ENV,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_QDRANT_COLLECTION,
    OpenAICompatibleEmbeddingClient,
    QdrantMemoryStore,
    attach_memory_citations_to_role_candidates,
    build_story_memory_chunks,
    derive_story_bible_facts,
    memory_result_from_chunk,
    search_memory_chunks,
)
from backend.app.domain.tool_registry import (
    ToolDefinition,
    ToolExecutionContext,
    ToolPermissionError,
    ToolRegistry,
    ToolValidationError,
    UnknownToolError,
    execute_tool_plan,
    summarize_tool_payload,
)
from backend.app.domain.voices import (
    VoiceResource,
    VoiceResourceCollection,
    default_voice_resources,
    generated_voice_content,
)
from backend.app.repositories.sqlite import SQLiteRepository
from scripts.container.download_models import ModelSpec, configured_models, ensure_model

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
DEFAULT_TTS_STARTUP_TIMEOUT_SECONDS = 300.0
SERVICE_NAME = "shuyi-agent"
SERVICE_VERSION = "0.7.0"
PUBLIC_BROWSER_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Credentials": "false",
    "Access-Control-Max-Age": "600",
}
MAX_NOVEL_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_REFERENCE_AUDIO_BYTES = 25 * 1024 * 1024


def _with_public_browser_cors(response: Response) -> Response:
    for header, value in PUBLIC_BROWSER_CORS_HEADERS.items():
        response.headers[header] = value
    return response


def _default_model_dir() -> Path:
    return Path(_service_env("SHUYI_MODEL_DIR", str(ROOT / "models"))).expanduser()


def _default_base_model_path() -> str:
    return str(_default_model_dir() / "Qwen3-TTS-12Hz-1.7B-Base")


def _default_voice_design_model_path() -> str:
    return str(_default_model_dir() / "Qwen3-TTS-12Hz-1.7B-VoiceDesign")


DEFAULT_BASE_MODEL_PATH = _default_base_model_path()
DEFAULT_VOICE_DESIGN_MODEL_PATH = _default_voice_design_model_path()


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
            "model_path": os.environ.get("QWEN3_TTS_MODEL_PATH", _default_base_model_path()),
            "voice_design_model_path": os.environ.get(
                "QWEN3_TTS_VOICE_DESIGN_MODEL_PATH",
                _default_voice_design_model_path(),
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


def _configured_context_window() -> int:
    raw = (
        os.environ.get("SHUYI_TEXT_MODEL_CONTEXT_WINDOW")
        or os.environ.get("SHUYI_CONTEXT_WINDOW")
        or ""
    )
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CONTEXT_WINDOW
    return value if value > 0 else DEFAULT_CONTEXT_WINDOW


def _trace_input_text(
    *,
    chapter_title: str,
    paragraphs: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    utterances_by_paragraph: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    paragraph_text = "\n\n".join(str(item.get("text") or "") for item in paragraphs)
    payload = {
        "chapter_title": chapter_title,
        "roles": roles,
        "paragraphs": paragraphs,
    }
    if utterances_by_paragraph is not None:
        payload["utterances_by_paragraph"] = utterances_by_paragraph
    return f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n章节正文：\n{paragraph_text}"


def _latest_raw_model_output(skill: Any) -> str:
    invocations = getattr(skill, "invocation_trace", None)
    if isinstance(invocations, list) and invocations:
        latest = invocations[-1]
        if isinstance(latest, dict) and latest.get("raw_model_output") is not None:
            return str(latest["raw_model_output"])
    return ""


def _build_agent_trace_payload(
    app: FastAPI,
    *,
    run_id: str,
    project_id: str,
    chapter_id: str,
    agent_id: str,
    input_text: str,
    parsed_output: dict[str, Any],
    raw_model_output: str,
    validation_status: str,
    validation_errors: list[Any],
    reflection_count: int,
    reflection_trace: list[Any],
    final_decision: str,
    human_review_count: int,
    duration_ms: int,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    agent = app.state.agent_registry.get(agent_id)
    provider = _text_model_provider_from_config(app)
    max_tokens = int(provider.get("max_tokens") or DEFAULT_RESERVED_OUTPUT_TOKENS)
    raw_output = raw_model_output or json.dumps(
        parsed_output, ensure_ascii=False, separators=(",", ":")
    )
    token_report = build_token_context_report(
        system_prompt=agent.prompt_text,
        input_text=input_text,
        output_text=raw_output,
        context_window=_configured_context_window(),
        reserved_output_tokens=max_tokens,
    )
    return {
        "run_id": run_id,
        "project_id": project_id or "default",
        "chapter_id": chapter_id,
        "agent_id": agent.agent_id,
        "agent_name": agent.display_name,
        "prompt_id": agent.prompt_id,
        "prompt_version": agent.prompt_version,
        "prompt_sha256": agent.prompt_sha256,
        "model_name": str(provider.get("model") or ""),
        "provider_base_url": str(provider.get("base_url") or ""),
        "temperature": 0,
        "max_tokens": max_tokens,
        "estimated_prompt_tokens": token_report["estimated_prompt_tokens"],
        "estimated_input_tokens": token_report["estimated_input_tokens"],
        "estimated_output_tokens": token_report["estimated_output_tokens"],
        "estimated_total_tokens": token_report["estimated_total_tokens"],
        "context_window": token_report["context_window"],
        "input_summary": summarize_for_trace(input_text),
        "raw_model_output": raw_output,
        "parsed_output": parsed_output,
        "validation_status": validation_status,
        "validation_errors": validation_errors,
        "reflection_count": reflection_count,
        "reflection_trace": reflection_trace,
        "final_decision": final_decision,
        "human_review_count": human_review_count,
        "duration_ms": duration_ms,
        "token_context_report": token_report,
        "tool_calls": tool_calls or [],
    }


def _save_dubbing_director_trace(
    app: FastAPI,
    repository: SQLiteRepository,
    *,
    thread_id: str,
    project_id: str,
    roles: list[dict[str, Any]],
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    workflow: DubbingWorkflow,
    result: Any,
    duration_ms: int,
) -> None:
    run = repository.get_agent_run(thread_id) or {}
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    chapter_id = str(checkpoint.get("chapter_id") or "")
    workbench = _state(app)["workbenches"].get(chapter_id)
    chapter_title = workbench.chapter.title if workbench else chapter_id
    paragraphs = (
        [_paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs]
        if workbench
        else []
    )
    parsed_output = result.to_dict()
    validation_errors = [result.failure] if getattr(result, "failure", None) else []
    human_review_count = sum(
        1
        for utterances in parsed_output.get("utterances_by_paragraph", {}).values()
        for utterance in utterances
        if utterance.get("needs_human_review")
    )
    repository.save_agent_trace(
        _build_agent_trace_payload(
            app,
            run_id=thread_id,
            project_id=project_id or "default",
            chapter_id=chapter_id,
            agent_id="dubbing_director",
            input_text=_trace_input_text(
                chapter_title=chapter_title,
                paragraphs=paragraphs,
                roles=roles,
                utterances_by_paragraph=utterances_by_paragraph,
            ),
            parsed_output=parsed_output,
            raw_model_output=_latest_raw_model_output(workflow.role_skill),
            validation_status="failed" if result.status == "failed" else "accepted",
            validation_errors=validation_errors,
            reflection_count=0,
            reflection_trace=[],
            final_decision=result.status,
            human_review_count=human_review_count,
            duration_ms=duration_ms,
        )
    )


def _idle_tts_deployment_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    tts = dict(config or _default_model_config()["tts"])
    return {
        "status": "idle",
        "stage": "idle",
        "progress": 0,
        "message": "尚未下载并部署 TTS 模型。",
        "can_retry": False,
        "error": None,
        "pid": None,
        "health": None,
        "model_path": tts.get("model_path"),
        "voice_design_model_path": tts.get("voice_design_model_path"),
        "attempt": 0,
        "updated_at": time.time(),
    }


def _get_tts_deployment_status(app: FastAPI) -> dict[str, Any]:
    with app.state.tts_deployment_lock:
        return dict(app.state.tts_deployment)


def _set_tts_deployment_status(app: FastAPI, **updates: Any) -> dict[str, Any]:
    with app.state.tts_deployment_lock:
        current = dict(app.state.tts_deployment)
        current.update(updates)
        current["updated_at"] = time.time()
        app.state.tts_deployment = current
        return dict(current)


def _normalize_tts_payload_config(app: FastAPI, payload: dict[str, Any] | None) -> dict[str, Any]:
    supplied_tts = (payload or {}).get("tts") or {}
    updates = {
        key: value
        for key, value in supplied_tts.items()
        if key in {"base_url", "model_path", "voice_design_model_path"}
    }
    return {**_state(app)["model_config"]["tts"], **updates}


def _absolute_model_target(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


def _tts_model_specs_for_config(config: dict[str, Any]) -> tuple[list[ModelSpec], dict[str, Any]]:
    base_target = _absolute_model_target(str(config.get("model_path") or _default_base_model_path()))
    voice_design_target = _absolute_model_target(
        str(config.get("voice_design_model_path") or _default_voice_design_model_path())
    )
    model_root = Path(_service_env("SHUYI_MODEL_DIR", str(base_target.parent))).expanduser()
    configured = configured_models(model_root)
    if len(configured) < 2:
        raise RuntimeError("TTS 模型配置不完整，至少需要 Base 与 VoiceDesign 两个模型。")
    base_spec, voice_design_spec = configured[:2]
    specs = [
        ModelSpec(
            modelscope_id=base_spec.modelscope_id,
            huggingface_id=base_spec.huggingface_id,
            modelscope_revision=base_spec.modelscope_revision,
            huggingface_revision=base_spec.huggingface_revision,
            target=base_target,
        ),
        ModelSpec(
            modelscope_id=voice_design_spec.modelscope_id,
            huggingface_id=voice_design_spec.huggingface_id,
            modelscope_revision=voice_design_spec.modelscope_revision,
            huggingface_revision=voice_design_spec.huggingface_revision,
            target=voice_design_target,
        ),
    ]
    normalized = {
        **config,
        "model_path": str(base_target),
        "voice_design_model_path": str(voice_design_target),
    }
    return specs, normalized


def _tts_command(config: dict[str, Any]) -> list[str]:
    base_url = str(config.get("base_url") or "http://127.0.0.1:7811")
    command = [
        os.environ.get("QWEN3_TTS_PYTHON", sys.executable),
        str(DEFAULT_TTS_SCRIPT),
        "--model-path",
        str(config.get("model_path") or _default_base_model_path()),
        "--host",
        "127.0.0.1",
        "--port",
        str(_port_from_base_url(base_url)),
        "--device",
        os.environ.get("QWEN3_TTS_DEVICE", os.environ.get("SHUYI_DEVICE", "cpu")),
    ]
    voice_design_model_path = str(config.get("voice_design_model_path") or "").strip()
    if voice_design_model_path:
        command.extend(["--voice-design-model-path", voice_design_model_path])
    return command


def _start_or_wait_tts_service(app: FastAPI, config: dict[str, Any]) -> tuple[int | None, dict[str, Any], str]:
    base_url = str(config.get("base_url") or "http://127.0.0.1:7811")
    current = _state(app).get("tts_process")
    if current is not None and current.poll() is None:
        health = _wait_for_tts_ready(current, base_url)
        return current.pid, health, "本地 TTS 服务已在运行，模型加载完成，VoiceDesign 已就绪"

    current_health = _fetch_tts_health(base_url)
    if _is_tts_ready(current_health):
        return None, current_health, "本地 TTS 服务已在运行，模型加载完成，VoiceDesign 已就绪"
    if current_health.get("reachable"):
        health = _wait_for_tts_ready(None, base_url)
        return None, health, "本地 TTS 服务模型加载完成，VoiceDesign 已就绪"

    process = _start_tts_process(_tts_command(config))
    _state(app)["tts_process"] = process
    health = _wait_for_tts_ready(process, base_url)
    return process.pid, health, "本地 TTS 服务启动成功，模型加载完成，VoiceDesign 已就绪"


def _run_tts_download_and_deploy(app: FastAPI, config: dict[str, Any], attempt: int) -> None:
    specs: list[ModelSpec] = []
    try:
        _set_tts_deployment_status(
            app,
            status="running",
            stage="checking",
            progress=5,
            message="正在检查 TTS 模型缓存与服务状态。",
            can_retry=False,
            error=None,
            attempt=attempt,
        )
        current_health = _fetch_tts_health(str(config.get("base_url") or "http://127.0.0.1:7811"))
        if _is_tts_ready(current_health):
            _set_tts_deployment_status(
                app,
                status="succeeded",
                stage="ready",
                progress=100,
                message="TTS 模型已经下载并部署完成。",
                health=current_health,
                pid=None,
                can_retry=False,
                model_path=config.get("model_path"),
                voice_design_model_path=config.get("voice_design_model_path"),
            )
            return

        specs, config = _tts_model_specs_for_config(config)
        _state(app)["model_config"]["tts"] = config
        for index, spec in enumerate(specs):
            _set_tts_deployment_status(
                app,
                status="running",
                stage="downloading",
                progress=10 + index * 25,
                message=f"正在下载或校验模型：{spec.target.name}",
                model_path=config.get("model_path"),
                voice_design_model_path=config.get("voice_design_model_path"),
            )
            result = ensure_model(spec)
            _set_tts_deployment_status(
                app,
                status="running",
                stage="downloading",
                progress=35 + index * 25,
                message=f"模型 {spec.target.name} 已就绪：{result}",
            )

        _set_tts_deployment_status(
            app,
            status="running",
            stage="deploying",
            progress=76,
            message="模型下载已完成，正在启动并部署本地 TTS 服务。",
        )
        try:
            pid, health, message = _start_or_wait_tts_service(app, config)
        except Exception as exc:  # noqa: BLE001 - 后台部署需要把失败反馈给前端轮询。
            _set_tts_deployment_status(
                app,
                status="failed",
                stage="deploying",
                progress=82,
                message=f"模型下载已完成，但部署失败：{exc}",
                error=str(exc),
                can_retry=True,
                pid=None,
            )
            return

        _set_tts_deployment_status(
            app,
            status="succeeded",
            stage="ready",
            progress=100,
            message=message,
            health=health,
            pid=pid,
            can_retry=False,
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 - 下载/校验失败同样通过状态反馈给前端。
        stage = "downloading" if specs else "checking"
        _set_tts_deployment_status(
            app,
            status="failed",
            stage=stage,
            progress=20,
            message=f"模型下载或校验失败：{exc}",
            error=str(exc),
            can_retry=True,
            pid=None,
        )

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
    data_root_value = _service_env("SHUYI_DATA_DIR").strip()
    data_root = Path(data_root_value).expanduser() if data_root_value else None
    repository = SQLiteRepository(data_root / "shuyi-agent.sqlite3" if data_root else ":memory:")
    repository.initialize()
    app.state.repository = repository
    app.state.data_root = data_root or DEFAULT_DATA_ROOT
    app.state.agent_registry = AgentRegistry.default()
    app.state.chapter_rule_dir = (
        data_root / "cache/chapter-rules" if data_root else CHAPTER_RULE_DIR
    )
    app.state.startup_ready = True
    app.state.require_tts_ready = _service_env("SHUYI_REQUIRE_TTS_READY", "0") == "1"
    app.state.secret_exchanges = {}
    app.state.text_model_api_key = ""
    app.state.tts_deployment_lock = threading.Lock()
    app.state.tts_deployment = _idle_tts_deployment_status(_default_model_config()["tts"])
    app.state.tts_synthesis_lock = threading.Lock()
    if repository.get_project(DEFAULT_PROJECT_ID) is None:
        repository.save_project(default_project(app.state.data_root))

    @app.middleware("http")
    async def versioned_api_boundary(request: Request, call_next):
        path = str(request.scope.get("path") or "")
        if request.method == "OPTIONS":
            return await call_next(request)
        if path.startswith("/api/") and not path.startswith("/api/v1/"):
            return JSONResponse(status_code=404, content={"detail": "接口不存在"})
        response = await call_next(request)
        if request.method in {"POST", "PATCH", "PUT", "DELETE"} and response.status_code < 400:
            try:
                save_runtime_state(repository, _state(app))
            except (OSError, RuntimeError, TypeError, ValueError):
                app.state.startup_ready = False
        return response

    @app.middleware("http")
    async def public_browser_cors(request: Request, call_next):
        if request.method == "OPTIONS":
            return Response(status_code=200, headers=PUBLIC_BROWSER_CORS_HEADERS)
        return _with_public_browser_cors(await call_next(request))

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
    app.state.tool_registry = _build_tool_registry(app, repository)

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

    @app.get("/api/v1/connection-test")
    async def connection_test() -> dict[str, Any]:
        try:
            repository.ping()
        except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"后端 API 连接失败：{exc}") from exc
        return {
            "ok": True,
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "message": "后端 API 连接成功",
        }

    def role_payload() -> dict[str, Any]:
        collection = _state(app)["roles"]
        return {
            "roles": [_public_role_to_dict(role) for role in collection.list()],
            "role_options": collection.utterance_role_options(),
        }

    @app.get("/api/v1/characters")
    async def list_v1_characters() -> dict[str, Any]:
        return role_payload()

    @app.get("/api/v1/model-config")
    async def get_v1_model_config() -> dict[str, Any]:
        return {
            "config": _redacted_model_config(
                _state(app)["model_config"],
                has_text_model_api_key=_has_text_model_api_key(app),
            )
        }

    @app.get("/api/v1/downloads/{category}/{filename:path}")
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

    @app.get("/api/v1/projects/{project_id}/downloads/exports/{filename:path}")
    async def download_project_export(project_id: str, filename: str):
        project = _require_project_with_roots(repository, app.state.data_root, project_id)
        directory = Path(project["output_roots"]["exports"]).resolve()
        target = (directory / filename).resolve()
        if not _is_inside(target, directory) or not target.is_file():
            raise HTTPException(status_code=404, detail="下载资源不存在")
        return FileResponse(target, filename=target.name)

    @app.get("/api/v1/projects")
    async def list_projects() -> dict[str, Any]:
        projects = [
            with_output_roots(project, app.state.data_root)
            for project in repository.list_projects()
        ]
        if not any(project["project_id"] == DEFAULT_PROJECT_ID for project in projects):
            project = default_project(app.state.data_root)
            repository.save_project(project)
            projects.insert(0, project)
        return {"projects": projects}

    @app.post("/api/v1/projects")
    async def create_project(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            project = project_from_payload(payload or {}, app.state.data_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        Path(project["output_roots"]["audio"]).mkdir(parents=True, exist_ok=True)
        Path(project["output_roots"]["exports"]).mkdir(parents=True, exist_ok=True)
        repository.save_project(project)
        return {"project": project}

    @app.get("/api/v1/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, Any]:
        safe_id = safe_project_id(project_id)
        project = repository.get_project(safe_id)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return {"project": with_output_roots(project, app.state.data_root)}

    @app.delete("/api/v1/projects/{project_id}")
    async def delete_project(project_id: str) -> dict[str, Any]:
        safe_id = safe_project_id(project_id)
        if safe_id == DEFAULT_PROJECT_ID:
            raise HTTPException(status_code=409, detail="默认项目不能删除")
        return {"project_id": safe_id, "deleted": repository.delete_project(safe_id)}

    @app.post("/api/v1/projects/{project_id}/quality-check")
    async def project_quality_check(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        quality_payload = _quality_payload_from_request(app, payload or {})
        return build_quality_report(project_id=safe_id, **quality_payload)

    @app.post("/api/v1/projects/{project_id}/review-queue")
    async def project_review_queue(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        payload = payload or {}
        quality_payload = _quality_payload_from_request(app, payload)
        report = build_quality_report(project_id=safe_id, **quality_payload)
        return build_review_queue(
            quality_report=report,
            filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else {},
        )

    @app.post("/api/v1/projects/{project_id}/utterances/long-text/detect")
    async def detect_project_long_utterances(
        project_id: str, payload: dict[str, Any] | None = None
    ):
        safe_id = _require_project(repository, project_id)
        payload = payload or {}
        max_chars = int(payload.get("max_utterance_chars") or payload.get("max_chars") or 120)
        items = detect_long_utterances(
            _utterances_by_paragraph_from_payload(payload),
            max_chars=max_chars,
        )
        return {"project_id": safe_id, "items": items, "total_count": len(items)}

    @app.post("/api/v1/projects/{project_id}/utterances/{utterance_id}/split-long-text")
    async def split_project_long_utterance(
        project_id: str,
        utterance_id: str,
        payload: dict[str, Any] | None = None,
    ):
        safe_id = _require_project(repository, project_id)
        payload = payload or {}
        try:
            result = split_long_utterance_groups(
                _utterances_by_paragraph_from_payload(payload),
                utterance_id=utterance_id,
                max_chars=int(payload.get("max_utterance_chars") or payload.get("max_chars") or 120),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"project_id": safe_id, **result}

    @app.post("/api/v1/projects/{project_id}/utterances/merge")
    async def merge_project_utterances(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        payload = payload or {}
        try:
            result = merge_utterance_groups(
                _utterances_by_paragraph_from_payload(payload),
                paragraph_id=str(payload.get("paragraph_id") or ""),
                utterance_ids=[str(item) for item in payload.get("utterance_ids") or []],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"project_id": safe_id, **result}

    @app.post("/api/v1/projects/{project_id}/utterances/bulk-role")
    async def bulk_update_project_utterance_role(
        project_id: str, payload: dict[str, Any] | None = None
    ):
        safe_id = _require_project(repository, project_id)
        payload = payload or {}
        result = bulk_update_role(
            _utterances_by_paragraph_from_payload(payload),
            utterance_ids=[str(item) for item in payload.get("utterance_ids") or []],
            role_id=str(payload.get("role_id") or ""),
            speaker_name=str(payload.get("speaker_name") or ""),
        )
        return {"project_id": safe_id, **result}

    @app.post("/api/v1/projects/{project_id}/utterances/retry-queue")
    async def prepare_project_utterance_retry_queue(
        project_id: str, payload: dict[str, Any] | None = None
    ):
        safe_id = _require_project(repository, project_id)
        payload = payload or {}
        result = prepare_retry_queue(
            _utterances_by_paragraph_from_payload(payload),
            utterance_ids=[str(item) for item in payload.get("utterance_ids") or []]
            if isinstance(payload.get("utterance_ids"), list)
            else None,
        )
        return {"project_id": safe_id, **result}

    @app.post("/api/v1/projects/{project_id}/memory/index")
    async def index_project_memory(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        payload = payload or {}
        chunks = build_story_memory_chunks(project_id=safe_id, payload=payload)
        facts = derive_story_bible_facts(project_id=safe_id, chunks=chunks, payload=payload)
        repository.replace_story_memory(project_id=safe_id, chunks=chunks, facts=facts)
        embedding_status, message = _try_vector_index_memory(app, safe_id, chunks)
        return {
            "project_id": safe_id,
            "status": "indexed" if chunks else "empty",
            "chunk_count": len(chunks),
            "fact_count": len(facts),
            "embedding_status": embedding_status,
            "message": message,
        }

    @app.post("/api/v1/projects/{project_id}/memory/search")
    async def search_project_memory(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        payload = payload or {}
        query = str(payload.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="检索 query 不能为空")
        top_k = max(1, min(int(payload.get("top_k") or 5), 20))
        vector_results, retrieval_mode, message = _try_vector_search_memory(
            project_id=safe_id,
            query=query,
            top_k=top_k,
        )
        if vector_results is not None:
            return {
                "project_id": safe_id,
                "query": query,
                "retrieval_mode": retrieval_mode,
                "message": message,
                "results": vector_results,
            }
        results = search_memory_chunks(
            chunks=repository.list_story_memory_chunks(safe_id),
            query=query,
            top_k=top_k,
        )
        return {
            "project_id": safe_id,
            "query": query,
            "retrieval_mode": "sqlite_lexical",
            "message": message,
            "results": results,
        }

    @app.get("/api/v1/projects/{project_id}/story-bible")
    async def get_story_bible(project_id: str):
        safe_id = _require_project(repository, project_id)
        return {"project_id": safe_id, "facts": repository.list_story_bible_facts(safe_id)}

    @app.post("/api/v1/projects/{project_id}/story-bible/facts")
    async def create_story_bible_fact(project_id: str, payload: dict[str, Any]):
        safe_id = _require_project(repository, project_id)
        try:
            fact = build_long_term_memory_fact(project_id=safe_id, payload=payload or {})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        repository.save_story_bible_fact(project_id=safe_id, fact=fact)
        return {"project_id": safe_id, "fact": fact}

    @app.get("/api/v1/projects/{project_id}/story-bible/memory-context")
    async def get_story_bible_memory_context(
        project_id: str,
        query: str = "",
        limit: int = 20,
    ):
        safe_id = _require_project(repository, project_id)
        return {
            "project_id": safe_id,
            "query": query,
            **build_story_memory_context(
                facts=repository.list_story_bible_facts(safe_id),
                query=query,
                limit=limit,
            ),
        }

    @app.patch("/api/v1/projects/{project_id}/story-bible/facts/{fact_id}")
    async def update_story_bible_fact(project_id: str, fact_id: str, payload: dict[str, Any]):
        safe_id = _require_project(repository, project_id)
        fact = repository.update_story_bible_fact(
            project_id=safe_id,
            fact_id=fact_id,
            updates=payload or {},
        )
        if fact is None:
            raise HTTPException(status_code=404, detail="Story Bible fact 不存在")
        return {"project_id": safe_id, "fact": fact}

    @app.get("/api/v1/projects/{project_id}/run-memory/{run_id}")
    async def get_run_memory(project_id: str, run_id: str):
        safe_id = _require_project(repository, project_id)
        memory = repository.get_run_memory(project_id=safe_id, run_id=run_id)
        if memory is None:
            raise HTTPException(status_code=404, detail="Run Memory 不存在")
        return {"project_id": safe_id, "run_memory": memory}

    @app.post("/api/v1/projects/{project_id}/planner/plan")
    async def plan_production_task(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        try:
            planner_run = build_production_planner_run(
                project_id=safe_id,
                payload=payload or {},
                registered_tools=_registered_tool_names(app.state.tool_registry),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _persist_planner_run(repository, planner_run)
        return {
            "project_id": safe_id,
            "planner_run": planner_run,
            "planner_policy": {
                "executor": "registered_tools_only",
                "failure_mode": "pause_with_recovery_suggestions",
                "reviewer": "checks_failed_and_pending_steps",
            },
        }

    @app.get("/api/v1/projects/{project_id}/planner/runs/{run_id}")
    async def get_production_planner_run(project_id: str, run_id: str):
        safe_id = _require_project(repository, project_id)
        planner_run = repository.get_planner_run(project_id=safe_id, run_id=run_id)
        if planner_run is None:
            raise HTTPException(status_code=404, detail="Planner run 不存在")
        return {"project_id": safe_id, "planner_run": planner_run}

    @app.post("/api/v1/projects/{project_id}/planner/execute")
    async def execute_production_plan(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        plan = payload or {}
        run_id = str(plan.get("run_id") or "")
        existing = repository.get_planner_run(project_id=safe_id, run_id=run_id) if run_id else None
        try:
            planner_run = (
                existing
                if existing is not None and not plan.get("steps")
                else planner_run_from_payload(
                    project_id=safe_id,
                    payload=plan,
                    registered_tools=_registered_tool_names(app.state.tool_registry),
                )
            )
            updated = execute_planner_run(
                planner_run=planner_run,
                registry=app.state.tool_registry,
                context=ToolExecutionContext(project_id=safe_id),
                max_steps=int(plan.get("max_steps") or 0) or None,
            )
        except UnknownToolError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ToolPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ToolValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _append_planner_events(repository, updated)
        _persist_planner_run(repository, updated)
        return {"project_id": safe_id, "planner_run": updated}

    @app.post("/api/v1/projects/{project_id}/planner/review")
    async def review_production_plan(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        plan = payload or {}
        run_id = str(plan.get("run_id") or "")
        existing = repository.get_planner_run(project_id=safe_id, run_id=run_id) if run_id else None
        try:
            planner_run = (
                existing
                if existing is not None and not plan.get("steps")
                else planner_run_from_payload(
                    project_id=safe_id,
                    payload=plan,
                    registered_tools=_registered_tool_names(app.state.tool_registry),
                )
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        review = review_planner_run(planner_run)
        updated = {
            **planner_run,
            "status": review["status"],
            "reflection": [*planner_run.get("reflection", []), review],
            "final_output": {"status": review["status"], "review": review},
            "updated_at": review["reviewed_at"],
        }
        _persist_planner_run(repository, updated)
        return {"project_id": safe_id, "planner_run": updated, "review": review}

    @app.get("/api/v1/tools")
    async def list_tools() -> dict[str, Any]:
        return {
            "tools": app.state.tool_registry.list_definitions(),
            "tool_call_format": {
                "tool_calls": [
                    {
                        "tool_name": "search_story_memory",
                        "arguments": {"query": "林舟", "top_k": 3},
                    }
                ]
            },
        }

    @app.post("/api/v1/projects/{project_id}/tools/execute")
    async def execute_project_tools(project_id: str, payload: dict[str, Any] | None = None):
        safe_id = _require_project(repository, project_id)
        plan = payload or {}
        started = time.perf_counter()
        try:
            result = execute_tool_plan(
                app.state.tool_registry,
                ToolExecutionContext(project_id=safe_id),
                plan,
            )
        except UnknownToolError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ToolPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ToolValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        run_id = str(plan.get("run_id") or f"tool-run-{secrets.token_hex(8)}")
        agent_id = str(plan.get("agent_id") or "role_analyzer")
        chapter_id = str(plan.get("chapter_id") or "")
        duration_ms = int((time.perf_counter() - started) * 1000)
        trace = _build_tool_call_trace_payload(
            app,
            run_id=run_id,
            project_id=safe_id,
            chapter_id=chapter_id,
            agent_id=agent_id,
            plan=plan,
            tool_results=result["tool_results"],
            duration_ms=duration_ms,
            final_decision=result["status"],
        )
        repository.save_agent_trace(trace)
        repository.save_run_memory(
            build_run_memory_snapshot(
                project_id=safe_id,
                run_id=run_id,
                payload=plan,
                tool_results=result["tool_results"],
                final_status=result["status"],
            )
        )
        return {
            "project_id": safe_id,
            "run_id": run_id,
            **result,
        }

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

    @app.get("/api/v1/agent-runs")
    async def list_agent_runs(project_id: str = "default", limit: int = 50) -> dict[str, Any]:
        return {
            "runs": repository.list_agent_traces(
                project_id=project_id or "default",
                limit=limit,
            )
        }

    @app.get("/api/v1/agent-runs/{run_id}")
    async def get_agent_run_trace(run_id: str, agent_id: str | None = None) -> dict[str, Any]:
        trace = repository.get_agent_trace(run_id, agent_id=agent_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="Agent 运行追踪不存在")
        return {"trace": trace}

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
        payload = payload or {}
        project_id = str(payload.get("project_id") or "default")
        state = _state(app)
        workbench = state["workbenches"].get(chapter_id)
        if workbench is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        workflow = _create_dubbing_workflow(app)
        paragraphs = [_paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs]
        existing_roles = [role.to_dict() for role in state["roles"].list()]
        started_at = time.perf_counter()
        try:
            result = workflow.start_role_analysis(
                chapter_id=chapter_id,
                chapter_title=workbench.chapter.title,
                paragraphs=paragraphs,
                existing_roles=existing_roles,
            )
        except MissingProviderCredential as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"角色分析 Agent 失败：{exc}") from exc
        memory_chunks = repository.list_story_memory_chunks(project_id)
        if memory_chunks:
            result = replace(
                result,
                role_candidates=attach_memory_citations_to_role_candidates(
                    result.role_candidates,
                    search=lambda query, top_k=3: search_memory_chunks(
                        chunks=memory_chunks,
                        query=query,
                        top_k=top_k,
                    ),
                ),
            )
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
        parsed_output = result.to_dict()
        repository.save_agent_trace(
            _build_agent_trace_payload(
                app,
                run_id=result.thread_id,
                project_id=project_id,
                chapter_id=chapter_id,
                agent_id="role_analyzer",
                input_text=_trace_input_text(
                    chapter_title=workbench.chapter.title,
                    paragraphs=paragraphs,
                    roles=existing_roles,
                ),
                parsed_output=parsed_output,
                raw_model_output=_latest_raw_model_output(workflow.role_skill),
                validation_status="accepted",
                validation_errors=[],
                reflection_count=0,
                reflection_trace=[],
                final_decision=result.status,
                human_review_count=sum(
                    1 for candidate in result.role_candidates if candidate.needs_human_review
                ),
                duration_ms=int((time.perf_counter() - started_at) * 1000),
            )
        )
        return result.to_dict()

    @app.post("/api/v1/agent-runs/{thread_id}/dubbing-arrangement")
    async def complete_dubbing_arrangement(
        thread_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = payload or {}
        workflow = _dubbing_workflow(app, thread_id)
        roles = _roles_for_dubbing_payload(app, payload)
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload)
        started_at = time.perf_counter()
        try:
            result = workflow.resume_after_roles(
                thread_id=thread_id,
                roles=roles,
                existing_utterances_by_paragraph=utterances_by_paragraph,
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
        _save_dubbing_director_trace(
            app,
            repository,
            thread_id=thread_id,
            project_id=str(payload.get("project_id") or "default"),
            roles=roles,
            utterances_by_paragraph=utterances_by_paragraph,
            workflow=workflow,
            result=result,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
        )
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
                started_at = time.perf_counter()
                try:
                    result = workflow.resume_after_roles(
                        thread_id=thread_id,
                        roles=roles,
                        existing_utterances_by_paragraph=utterances_by_paragraph,
                        on_role_selected=lambda event: emit("role_selected", event),
                    )
                    event_name = "failed" if result.status == "failed" else "completed"
                    emit(event_name, result.to_dict())
                    _save_dubbing_director_trace(
                        app,
                        repository,
                        thread_id=thread_id,
                        project_id=str((payload or {}).get("project_id") or "default"),
                        roles=roles,
                        utterances_by_paragraph=utterances_by_paragraph,
                        workflow=workflow,
                        result=result,
                        duration_ms=int((time.perf_counter() - started_at) * 1000),
                    )
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
        except TTSServiceError:
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

    @app.post("/api/v1/voice-profiles/export")
    async def export_voice_resources() -> dict[str, Any]:
        export_dir = OUTPUT_EXPORT_DIR / f"voice-library-{int(time.time())}"
        export_dir.mkdir(parents=True, exist_ok=True)
        media_dir = export_dir / "voice-profiles"
        media_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "exported_at": time.time(),
            "voices": [],
        }
        copied_count = 0
        for voice in _state(app)["voices"].list():
            item = voice.to_dict()
            audio_path = _resolve_audio_path(str(voice.reference_audio_path or ""))
            if audio_path.is_file() and _is_allowed_audio_path(audio_path):
                filename = _safe_audio_filename(f"{voice.voice_id}{audio_path.suffix}")
                target = media_dir / filename
                shutil.copy2(audio_path, target)
                item["exported_audio_file"] = f"voice-profiles/{filename}"
                copied_count += 1
            else:
                item["exported_audio_file"] = None
                item["export_error"] = "参考音频不存在或不在受控目录内"
            manifest["voices"].append(item)

        (export_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        archive_path = Path(
            await asyncio.to_thread(shutil.make_archive, str(export_dir), "zip", export_dir)
        )
        return {
            "status": "completed",
            "voice_count": len(manifest["voices"]),
            "audio_count": copied_count,
            "download_url": f"/api/v1/downloads/exports/{archive_path.name}",
            "message": f"音色库导出完成：{len(manifest['voices'])} 个音色，{copied_count} 个音频资源。",
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

    @app.get("/api/v1/voice-profiles/{voice_id}/audio")
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

    @app.post("/api/v1/model-config/models/test")
    async def test_model_apis(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if payload.get("text_model_secret"):
            _set_text_model_api_key_from_exchange(app, payload["text_model_secret"])

        supplied_text = payload.get("text_model") or {}
        text_config = {
            **_state(app)["model_config"]["text_model"],
            **{key: value for key, value in supplied_text.items() if key in {"base_url", "model"}},
            "api_key": _api_key_lookup_from_config(app)("SHUYI_TEXT_MODEL_API_KEY"),
        }
        supplied_tts = payload.get("tts") or {}
        tts_config = {
            **_state(app)["model_config"]["tts"],
            **{key: value for key, value in supplied_tts.items() if key in {"base_url", "model_path", "voice_design_model_path"}},
        }
        _state(app)["model_config"]["tts"] = tts_config

        models: dict[str, Any] = {}
        failures: list[str] = []
        try:
            await _test_model_link(text_config)
            models["text_model"] = {"ok": True, "message": "文本模型 API 正常"}
        except HTTPException as exc:
            message = f"文本模型 API 测试失败：{exc.detail}"
            models["text_model"] = {"ok": False, "message": message}
            failures.append(message)
        except (OSError, RuntimeError, TypeError, ValueError, urllib.error.URLError) as exc:
            message = f"文本模型 API 测试失败：{exc}"
            models["text_model"] = {"ok": False, "message": message}
            failures.append(message)

        base_url = str(tts_config.get("base_url") or "http://127.0.0.1:7811")
        health = await asyncio.to_thread(_fetch_tts_health, base_url)
        if _is_tts_ready(health):
            models["tts"] = {"ok": True, "message": "TTS模型 API 正常，Base 与 VoiceDesign 均已就绪", "health": health}
        else:
            message = f"TTS模型 API 测试失败：{_format_tts_not_ready_message(health)}"
            models["tts"] = {"ok": False, "message": message, "health": health}
            failures.append(message)

        if failures:
            raise HTTPException(status_code=503, detail="；".join(failures))
        return {
            "ok": True,
            "message": "模型 API 测试成功：文本模型与 TTS模型均可用",
            "models": models,
        }

    @app.get("/api/v1/model-config/tts/deployment")
    async def get_tts_deployment_status() -> dict[str, Any]:
        return {"deployment": _get_tts_deployment_status(app)}

    @app.post("/api/v1/model-config/tts/deploy")
    async def deploy_tts_models(payload: dict[str, Any] | None = None):
        config = _normalize_tts_payload_config(app, payload)
        _state(app)["model_config"]["tts"] = config
        with app.state.tts_deployment_lock:
            current = dict(app.state.tts_deployment)
            if current.get("status") == "running":
                return JSONResponse(status_code=202, content={"deployment": current})
            if current.get("status") == "succeeded":
                health = _fetch_tts_health(str(config.get("base_url") or "http://127.0.0.1:7811"))
                if _is_tts_ready(health):
                    current.update(
                        {
                            "health": health,
                            "progress": 100,
                            "message": "TTS 模型已经下载并部署完成。",
                            "updated_at": time.time(),
                        }
                    )
                    app.state.tts_deployment = current
                    return {"deployment": current}
            attempt = int(current.get("attempt") or 0) + 1
            running = {
                **_idle_tts_deployment_status(config),
                "status": "running",
                "stage": "checking",
                "progress": 1,
                "message": "已开始后台下载并部署 TTS 模型。",
                "attempt": attempt,
                "updated_at": time.time(),
            }
            app.state.tts_deployment = running
        thread = threading.Thread(
            target=_run_tts_download_and_deploy,
            args=(app, config, attempt),
            daemon=True,
        )
        thread.start()
        return JSONResponse(status_code=202, content={"deployment": running})

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
                _synthesize_local_qwen3_serialized,
                app,
                request,
                output_path,
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
            if not _should_return_substitute_tts_audio(exc):
                message = _single_utterance_tts_error_message(exc)
                error_job = VoiceJob(
                    **{
                        **job.to_dict(),
                        "status": "failed",
                        "error": message,
                    }
                )
                _state(app)["voice_jobs"][job_id] = error_job
                raise HTTPException(status_code=422, detail=message) from exc
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
            results: list[dict[str, Any]] = []
            languages = list(request.get("languages") or [])
            for index, (statement_id, text, output_path) in enumerate(
                zip(request["statement_ids"], request["texts"], output_paths, strict=True)
            ):
                line_request = {
                    "input": text,
                    "audio_sample_path": request.get("reference_audio_path"),
                    "ref_text": request.get("reference_text") or "",
                    "language": languages[index] if index < len(languages) else "Auto",
                    "response_format": "wav",
                    "x_vector_only": bool(request.get("x_vector_only", False)),
                }
                try:
                    duration = _synthesize_local_qwen3_serialized(app, line_request, output_path)
                except (TTSTextLimitError, TTSServiceError, ValueError, RuntimeError, OSError) as exc:
                    results.append(
                        {
                            "statement_id": statement_id,
                            "error": _single_utterance_tts_error_message(exc),
                        }
                    )
                    continue
                results.append(
                    {
                        "statement_id": statement_id,
                        "audio_path": str(output_path),
                        "audio_duration": duration,
                        "provider": "local-qwen3-tts",
                        "model": "Qwen3-TTS",
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
        roles = _roles_for_export_payload(app, payload or {})
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload or {})
        chapter_title = str((payload or {}).get("chapter_title") or chapter_id)
        export_options = _export_options_from_payload(payload or {})
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
            **export_options,
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
            "manifest_path": report.manifest_path,
            "full_audio_path": report.full_audio_path,
            "full_mp3_path": report.full_mp3_path,
            "package_files": report.package_files,
        }

    @app.post("/api/v1/projects/{project_id}/exports/{chapter_id}")
    async def export_project_chapter_audio_endpoint(
        project_id: str, chapter_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        project = _require_project_with_roots(repository, app.state.data_root, project_id)
        export_root = Path(project["output_roots"]["exports"])
        export_root.mkdir(parents=True, exist_ok=True)
        roles = _roles_for_export_payload(app, payload or {})
        utterances_by_paragraph = _utterances_by_paragraph_from_payload(payload or {})
        chapter_title = str((payload or {}).get("chapter_title") or chapter_id)
        export_options = _export_options_from_payload(payload or {})
        export_dir = export_root / (
            f"{_safe_audio_filename(chapter_id).removesuffix('.wav')}-{int(time.time())}"
        )
        report = await asyncio.to_thread(
            export_chapter_audio,
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            utterances_by_paragraph=utterances_by_paragraph,
            roles=roles,
            output_dir=export_dir,
            **export_options,
        )
        archive_path = Path(
            await asyncio.to_thread(shutil.make_archive, str(export_dir), "zip", export_dir)
        )
        safe_id = str(project["project_id"])
        return {
            "project_id": safe_id,
            "status": report.status,
            "item_count": report.item_count,
            "missing_count": report.missing_count,
            "message": report.message,
            "download_url": f"/api/v1/projects/{safe_id}/downloads/exports/{archive_path.name}",
            "manifest_path": report.manifest_path,
            "full_audio_path": report.full_audio_path,
            "full_mp3_path": report.full_mp3_path,
            "package_files": report.package_files,
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


def _roles_for_export_payload(app: FastAPI, payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_roles = payload.get("roles")
    if isinstance(raw_roles, list):
        return [dict(role) for role in raw_roles if isinstance(role, dict)]
    return [role.to_dict() for role in _state(app)["roles"].list()]


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


def _embedding_provider_from_env() -> dict[str, Any]:
    return {
        "base_url": _service_env("SHUYI_EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
        "model": _service_env("SHUYI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        "api_key_env": _service_env("SHUYI_EMBEDDING_API_KEY_ENV", DEFAULT_EMBEDDING_API_KEY_ENV),
        "timeout_seconds": int(_service_env("SHUYI_EMBEDDING_TIMEOUT_SECONDS", "60")),
    }


def _try_vector_index_memory(
    _app: FastAPI,
    project_id: str,
    chunks: list[dict[str, Any]],
) -> tuple[str, str]:
    if not chunks:
        return "skipped_empty", "没有可索引的 Story Memory chunk。"
    provider = _embedding_provider_from_env()
    try:
        embeddings = OpenAICompatibleEmbeddingClient(
            provider=provider,
            api_key_lookup=os.environ.get,
        ).embed_texts([str(chunk.get("text") or "") for chunk in chunks])
    except MissingProviderCredential:
        return (
            "skipped_missing_api_key",
            f"未配置 {provider['api_key_env']}，已保存 SQLite 文本索引并跳过向量化。",
        )
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return "embedding_failed", f"Embedding 请求失败，已保留 SQLite 文本索引：{exc}"
    qdrant_url = _service_env("SHUYI_QDRANT_URL", "").strip()
    if not qdrant_url:
        return "embedded_no_vector_store", "已生成 embedding，但未配置 SHUYI_QDRANT_URL。"
    if not embeddings:
        return "skipped_empty_embedding", "Embedding API 未返回可用向量。"
    collection_name = _service_env("SHUYI_QDRANT_COLLECTION", DEFAULT_QDRANT_COLLECTION)
    store = QdrantMemoryStore(
        base_url=qdrant_url,
        collection_name=collection_name,
    )
    try:
        store.ensure_collection(len(embeddings[0]))
        store.upsert(project_id=project_id, chunks=chunks, embeddings=embeddings)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return "qdrant_failed", f"Qdrant 写入失败，已保留 SQLite 文本索引：{exc}"
    return "qdrant_indexed", f"已写入 Qdrant collection：{collection_name}。"


def _try_vector_search_memory(
    *,
    project_id: str,
    query: str,
    top_k: int,
) -> tuple[list[dict[str, Any]] | None, str, str]:
    qdrant_url = _service_env("SHUYI_QDRANT_URL", "").strip()
    if not qdrant_url:
        return None, "sqlite_lexical", "未配置 SHUYI_QDRANT_URL，使用 SQLite 文本检索。"

    provider = _embedding_provider_from_env()
    try:
        embeddings = OpenAICompatibleEmbeddingClient(
            provider=provider,
            api_key_lookup=os.environ.get,
        ).embed_texts([query])
    except MissingProviderCredential:
        return (
            None,
            "sqlite_lexical",
            f"未配置 {provider['api_key_env']}，使用 SQLite 文本检索。",
        )
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return None, "sqlite_lexical", f"Embedding 请求失败，使用 SQLite 文本检索：{exc}"

    if not embeddings:
        return None, "sqlite_lexical", "Embedding API 未返回可用向量，使用 SQLite 文本检索。"

    store = QdrantMemoryStore(
        base_url=qdrant_url,
        collection_name=_service_env("SHUYI_QDRANT_COLLECTION", DEFAULT_QDRANT_COLLECTION),
    )
    try:
        response = store.search(project_id=project_id, embedding=embeddings[0], top_k=top_k)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return None, "sqlite_lexical", f"Qdrant 检索失败，使用 SQLite 文本检索：{exc}"
    return _memory_results_from_qdrant_response(response, query=query), "qdrant_vector", "已使用 Qdrant 向量检索。"


def _memory_results_from_qdrant_response(
    response: dict[str, Any],
    *,
    query: str,
) -> list[dict[str, Any]]:
    hits = response.get("result")
    if not isinstance(hits, list):
        return []
    results: list[dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, dict) or not isinstance(hit.get("payload"), dict):
            continue
        chunk = hit["payload"]
        required = {"chunk_id", "project_id", "source_type", "text"}
        if not required.issubset(chunk):
            continue
        results.append(
            memory_result_from_chunk(
                chunk=chunk,
                score=float(hit.get("score") or 0),
                query=query,
            )
        )
    return results


def _build_tool_registry(app: FastAPI, repository: SQLiteRepository) -> ToolRegistry:
    registry = ToolRegistry()

    def register(
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        permission_scope: str,
        implementation,
        timeout_seconds: int = 10,
    ) -> None:
        registry.register(
            ToolDefinition(
                tool_name=tool_name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                permission_scope=permission_scope,
                timeout_seconds=timeout_seconds,
                implementation=implementation,
            )
        )

    register(
        "search_story_memory",
        "Search project Story Memory and return grounded source citations.",
        _object_schema({"query": "string", "top_k": "integer", "project_id": "string"}, ["query"]),
        _object_schema({"retrieval_mode": "string", "results": "array"}),
        "project:memory:read",
        lambda context, arguments: _tool_search_story_memory(repository, context, arguments),
    )
    register(
        "get_project_status",
        "Build the current project quality report from supplied or active workflow state.",
        _object_schema(
            {
                "chapters": "array",
                "roles": "array",
                "utterances_by_paragraph": "object",
                "max_utterance_chars": "integer",
                "project_id": "string",
            }
        ),
        _object_schema({"quality_report": "object"}),
        "project:status:read",
        lambda context, arguments: {
            "quality_report": build_quality_report(
                project_id=context.project_id,
                **_quality_payload_from_request(app, arguments),
            )
        },
    )
    register(
        "list_roles",
        "List known roles for the current project workspace.",
        _object_schema({"project_id": "string"}),
        _object_schema({"roles": "array"}),
        "project:roles:read",
        lambda _context, _arguments: {
            "roles": [_public_role_to_dict(role) for role in _state(app)["roles"].list()]
        },
    )
    register(
        "get_role_profile",
        "Fetch one role profile by role_id or name.",
        _object_schema({"role_id": "string", "name": "string", "project_id": "string"}),
        _object_schema({"role": "object"}),
        "project:roles:read",
        lambda _context, arguments: _tool_get_role_profile(app, arguments),
    )
    register(
        "query_utterances",
        "Query utterances by status, role, paragraph, or length constraints.",
        _object_schema(
            {
                "utterances_by_paragraph": "object",
                "status": "string",
                "role_id": "string",
                "paragraph_id": "string",
                "max_chars": "integer",
                "project_id": "string",
            }
        ),
        _object_schema({"items": "array", "total_count": "integer"}),
        "project:utterances:read",
        lambda _context, arguments: _tool_query_utterances(arguments),
    )
    register(
        "suggest_long_text_split",
        "Suggest conservative punctuation-based splits for long TTS text.",
        _object_schema({"text": "string", "max_chars": "integer", "project_id": "string"}, ["text"]),
        _object_schema({"segments": "array", "text_conservation": "object"}),
        "project:utterances:write-suggestion",
        lambda _context, arguments: _tool_suggest_long_text_split(arguments),
    )
    register(
        "check_text_conservation",
        "Check whether split segments exactly preserve original text.",
        _object_schema(
            {"original_text": "string", "segments": "array", "project_id": "string"},
            ["original_text", "segments"],
        ),
        _object_schema({"matches": "boolean"}),
        "project:utterances:validate",
        lambda _context, arguments: _tool_check_text_conservation(arguments),
    )
    register(
        "check_tts_health",
        "Check local TTS service health without exposing credentials.",
        _object_schema({"base_url": "string", "project_id": "string"}),
        _object_schema({"ready": "boolean", "health": "object"}),
        "project:tts:read",
        lambda _context, arguments: _tool_check_tts_health(app, arguments),
    )
    register(
        "generate_voice_preview",
        "Generate or dry-run a voice preview request through the controlled TTS path.",
        _object_schema(
            {
                "name": "string",
                "description": "string",
                "reference_text": "string",
                "dry_run": "boolean",
                "allow_audio_generation": "boolean",
                "project_id": "string",
            },
            ["name", "description"],
        ),
        _object_schema({"status": "string", "preview_text": "string", "audio_url": "string"}),
        "project:tts:write",
        lambda _context, arguments: _tool_generate_voice_preview(app, arguments),
        timeout_seconds=30,
    )
    register(
        "lookup_pronunciation",
        "Look up pronunciation facts from project Story Bible and glossary chunks.",
        _object_schema({"term": "string", "project_id": "string"}, ["term"]),
        _object_schema({"facts": "array"}),
        "project:memory:read",
        lambda context, arguments: _tool_lookup_pronunciation(repository, context, arguments),
    )
    return registry


def _object_schema(
    properties: dict[str, str], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required or [],
        "properties": {name: {"type": kind} for name, kind in properties.items()},
    }


def _tool_search_story_memory(
    repository: SQLiteRepository,
    context: ToolExecutionContext,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    top_k = max(1, min(int(arguments.get("top_k") or 5), 20))
    vector_results, retrieval_mode, message = _try_vector_search_memory(
        project_id=context.project_id,
        query=query,
        top_k=top_k,
    )
    if vector_results is not None:
        return {"retrieval_mode": retrieval_mode, "message": message, "results": vector_results}
    results = search_memory_chunks(
        chunks=repository.list_story_memory_chunks(context.project_id),
        query=query,
        top_k=top_k,
    )
    return {"retrieval_mode": "sqlite_lexical", "message": message, "results": results}


def _tool_get_role_profile(app: FastAPI, arguments: dict[str, Any]) -> dict[str, Any]:
    role_id = str(arguments.get("role_id") or "").strip()
    name = str(arguments.get("name") or "").strip()
    for role in _state(app)["roles"].list():
        payload = _public_role_to_dict(role)
        if (role_id and payload.get("role_id") == role_id) or (name and payload.get("name") == name):
            return {"role": payload}
    raise ValueError("角色不存在")


def _tool_query_utterances(arguments: dict[str, Any]) -> dict[str, Any]:
    utterances_by_paragraph = _utterances_by_paragraph_from_payload(arguments)
    status = str(arguments.get("status") or "").strip()
    role_id = str(arguments.get("role_id") or "").strip()
    paragraph_filter = str(arguments.get("paragraph_id") or "").strip()
    max_chars = int(arguments.get("max_chars") or arguments.get("max_utterance_chars") or 120)
    items: list[dict[str, Any]] = []
    for paragraph_id, utterances in utterances_by_paragraph.items():
        if paragraph_filter and paragraph_id != paragraph_filter:
            continue
        for utterance in utterances:
            item_role_id = str(utterance.get("speaker_role_id") or utterance.get("role_id") or "")
            if role_id and item_role_id != role_id:
                continue
            if status and not _utterance_matches_tool_status(utterance, status, max_chars=max_chars):
                continue
            items.append({**utterance, "paragraph_id": str(utterance.get("paragraph_id") or paragraph_id)})
    return {"items": items, "total_count": len(items)}


def _utterance_matches_tool_status(
    utterance: dict[str, Any], status: str, *, max_chars: int
) -> bool:
    role_id = str(utterance.get("speaker_role_id") or utterance.get("role_id") or "")
    if status == "needs_human_review":
        return bool(utterance.get("needs_human_review"))
    if status == "unselected_role":
        return not role_id
    if status == "dubbing_failed":
        return _tool_is_audio_failed(utterance)
    if status == "undubbed":
        return bool(role_id) and not _tool_has_audio(utterance) and not _tool_is_audio_failed(utterance)
    if status == "long_utterance":
        return len(str(utterance.get("text") or "")) > max_chars
    return True


def _tool_has_audio(utterance: dict[str, Any]) -> bool:
    return bool(utterance.get("audio_url") or utterance.get("audio_path"))


def _tool_is_audio_failed(utterance: dict[str, Any]) -> bool:
    return bool(utterance.get("audio_error")) or str(
        utterance.get("audio_status") or ""
    ).lower() == "failed"


def _tool_suggest_long_text_split(arguments: dict[str, Any]) -> dict[str, Any]:
    text = str(arguments.get("text") or "")
    max_chars = max(1, int(arguments.get("max_chars") or 120))
    segments = split_text_for_tts(text, max_chars=max_chars)
    return {
        "segments": segments,
        "segment_count": len(segments),
        "text_conservation": text_conservation_report(text, segments),
    }


def _tool_check_text_conservation(arguments: dict[str, Any]) -> dict[str, Any]:
    original = str(arguments.get("original_text") or "")
    segments = [str(item) for item in arguments.get("segments") or []]
    return text_conservation_report(original, segments)


def _tool_check_tts_health(app: FastAPI, arguments: dict[str, Any]) -> dict[str, Any]:
    base_url = str(
        arguments.get("base_url") or _state(app)["model_config"]["tts"].get("base_url") or ""
    )
    health = _fetch_tts_health(base_url or "http://127.0.0.1:7811")
    return {"ready": _is_tts_ready(health), "health": health}


def _tool_generate_voice_preview(app: FastAPI, arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    description = str(arguments.get("description") or "").strip()
    reference_text = str(arguments.get("reference_text") or "").strip() or generated_voice_content(
        name, description
    )
    if bool(arguments.get("dry_run", True)) or not bool(arguments.get("allow_audio_generation")):
        return {"status": "dry_run", "preview_text": reference_text, "audio_url": ""}
    preview_id = f"preview-{len(_state(app)['voice_previews']) + 1:04d}"
    output_path = OUTPUT_VOICE_RESOURCE_DIR / f"{preview_id}.wav"
    duration_seconds = _write_substitute_wav(output_path)
    resource = VoiceResource(
        voice_id=preview_id,
        name=name,
        description=description,
        reference_text=reference_text,
        reference_audio_path=str(output_path),
        generated=True,
        playable_audio_path=str(output_path),
    )
    _state(app)["voice_previews"][preview_id] = resource
    return {
        "status": "generated",
        "preview_text": reference_text,
        "audio_url": f"/api/v1/downloads/voice-profiles/{preview_id}.wav",
        "duration_seconds": duration_seconds,
    }


def _tool_lookup_pronunciation(
    repository: SQLiteRepository,
    context: ToolExecutionContext,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    term = str(arguments.get("term") or "").strip()
    memory_context = build_story_memory_context(
        facts=[
            fact
            for fact in repository.list_story_bible_facts(context.project_id)
            if str(fact.get("subject") or "") == term and fact.get("predicate") == "pronunciation"
        ],
        query=term,
    )
    facts = memory_context["facts_for_prompt"]
    glossary_chunks = [
        chunk
        for chunk in repository.list_story_memory_chunks(context.project_id)
        if chunk.get("source_type") == "glossary" and term in str(chunk.get("text") or "")
    ]
    return {
        "term": term,
        "facts": facts,
        "candidate_facts": memory_context["candidate_facts"],
        "rejected_facts": memory_context["rejected_facts"],
        "glossary_chunks": glossary_chunks,
    }


def _build_tool_call_trace_payload(
    app: FastAPI,
    *,
    run_id: str,
    project_id: str,
    chapter_id: str,
    agent_id: str,
    plan: dict[str, Any],
    tool_results: list[dict[str, Any]],
    duration_ms: int,
    final_decision: str,
) -> dict[str, Any]:
    try:
        agent = app.state.agent_registry.get(agent_id)
        prompt_text = agent.prompt_text
        agent_name = agent.display_name
        prompt_id = agent.prompt_id
        prompt_version = agent.prompt_version
        prompt_sha256 = agent.prompt_sha256
    except KeyError:
        prompt_text = "Tool Calling Registry executes declared project-scoped tools only."
        agent_name = "Tool Calling Registry"
        prompt_id = "tool_registry"
        prompt_version = "1"
        prompt_sha256 = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    provider = _text_model_provider_from_config(app)
    input_text = summarize_tool_payload(plan, max_chars=2000)
    parsed_output = {"tool_results": tool_results}
    raw_output = json.dumps(parsed_output, ensure_ascii=False, separators=(",", ":"))
    max_tokens = int(provider.get("max_tokens") or DEFAULT_RESERVED_OUTPUT_TOKENS)
    token_report = build_token_context_report(
        system_prompt=prompt_text,
        input_text=input_text,
        output_text=raw_output,
        context_window=_configured_context_window(),
        reserved_output_tokens=max_tokens,
    )
    failures = [item for item in tool_results if item.get("status") == "failed"]
    return {
        "run_id": run_id,
        "project_id": project_id or "default",
        "chapter_id": chapter_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "model_name": str(provider.get("model") or ""),
        "provider_base_url": str(provider.get("base_url") or ""),
        "temperature": 0,
        "max_tokens": max_tokens,
        "estimated_prompt_tokens": token_report["estimated_prompt_tokens"],
        "estimated_input_tokens": token_report["estimated_input_tokens"],
        "estimated_output_tokens": token_report["estimated_output_tokens"],
        "estimated_total_tokens": token_report["estimated_total_tokens"],
        "context_window": token_report["context_window"],
        "input_summary": summarize_for_trace(input_text),
        "raw_model_output": raw_output,
        "parsed_output": parsed_output,
        "validation_status": "failed" if failures else "accepted",
        "validation_errors": failures,
        "reflection_count": 0,
        "reflection_trace": [],
        "final_decision": final_decision,
        "human_review_count": 0,
        "duration_ms": duration_ms,
        "token_context_report": token_report,
        "tool_calls": tool_results,
    }


def _require_project(repository: SQLiteRepository, project_id: str) -> str:
    try:
        safe_id = safe_project_id(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if repository.get_project(safe_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return safe_id


def _require_project_with_roots(
    repository: SQLiteRepository, data_root: Path, project_id: str
) -> dict[str, Any]:
    safe_id = _require_project(repository, project_id)
    project = repository.get_project(safe_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return with_output_roots(project, data_root)


def _export_options_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_formats = payload.get("export_formats") or payload.get("formats") or ["wav", "mp3"]
    if not isinstance(raw_formats, list):
        raw_formats = [raw_formats]
    return {
        "pause_ms": int(payload.get("pause_ms") or 300),
        "speed": float(payload.get("speed") or 1.0),
        "trim_silence": bool(payload.get("trim_silence", False)),
        "normalize_audio": bool(
            payload.get("normalize_audio", payload.get("loudness_normalization", False))
        ),
        "target_peak": float(payload.get("target_peak") or 0.9),
        "export_formats": [str(item) for item in raw_formats if str(item).strip()],
    }


def _registered_tool_names(registry: ToolRegistry) -> set[str]:
    return {str(definition["tool_name"]) for definition in registry.list_definitions()}


def _persist_planner_run(repository: SQLiteRepository, planner_run: dict[str, Any]) -> None:
    repository.save_planner_run(planner_run)
    repository.save_agent_run(
        run_id=str(planner_run["run_id"]),
        agent_id=PLANNER_AGENT_ID,
        status=str(planner_run.get("status") or "planned"),
        checkpoint=planner_run,
    )
    repository.save_run_memory(
        build_run_memory_snapshot(
            project_id=str(planner_run["project_id"]),
            run_id=str(planner_run["run_id"]),
            payload=planner_run_to_memory_payload(planner_run),
            tool_results=planner_run.get("tool_results") or [],
            final_status=str(planner_run.get("status") or "planned"),
        )
    )


def _append_planner_events(repository: SQLiteRepository, planner_run: dict[str, Any]) -> None:
    run_id = str(planner_run.get("run_id") or "")
    if not run_id:
        return
    for sequence, step in enumerate(planner_run.get("steps") or [], start=1):
        if not isinstance(step, dict) or step.get("status") == "pending":
            continue
        repository.append_event(
            run_id=run_id,
            sequence=sequence,
            event_type=f"planner_step_{step.get('status')}",
            payload={
                "project_id": planner_run.get("project_id"),
                "step_id": step.get("step_id"),
                "title": step.get("title"),
                "status": step.get("status"),
                "tool_name": (step.get("tool_call") or {}).get("tool_name")
                if isinstance(step.get("tool_call"), dict)
                else "",
                "failure": (step.get("tool_result") or {}).get("failure")
                if isinstance(step.get("tool_result"), dict)
                else None,
            },
        )


def _quality_payload_from_request(app: FastAPI, payload: dict[str, Any]) -> dict[str, Any]:
    chapters = payload.get("chapters")
    if not isinstance(chapters, list):
        chapters = _chapters_for_quality_payload(app)
    roles = payload.get("roles")
    if not isinstance(roles, list):
        roles = [role.to_dict() for role in _state(app)["roles"].list()]
    return {
        "chapters": [dict(item) for item in chapters if isinstance(item, dict)],
        "roles": [dict(item) for item in roles if isinstance(item, dict)],
        "utterances_by_paragraph": _utterances_by_paragraph_from_payload(payload),
        "max_utterance_chars": int(payload.get("max_utterance_chars") or 120),
    }


def _chapters_for_quality_payload(app: FastAPI) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for chapter in _state(app)["chapters"]:
        workbench = _state(app)["workbenches"].get(chapter.chapter_id)
        paragraphs = (
            [_paragraph_to_dict(paragraph) for paragraph in workbench.visible_paragraphs]
            if workbench
            else []
        )
        chapters.append(
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "paragraphs": paragraphs,
            }
        )
    return chapters


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


def _synthesize_local_qwen3_serialized(
    app: FastAPI,
    request: dict[str, Any],
    output_path: Path,
) -> float:
    with app.state.tts_synthesis_lock:
        return synthesize_local_qwen3(
            request,
            output_path=output_path,
            service_base_url=_state(app)["model_config"]["tts"].get("base_url"),
        )


def _should_return_substitute_tts_audio(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "connection refused",
            "connection reset",
            "failed to establish",
            "name or service not known",
            "no route to host",
            "本地 qwen3-tts 不可用",
            "不启动 tts",
        )
    )


def _single_utterance_tts_error_message(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, TTSTextLimitError):
        return message
    suffix = "这条台词生成失败，请拆分台词生成后重试。"
    return message if suffix in message else f"{message}；{suffix}"


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
