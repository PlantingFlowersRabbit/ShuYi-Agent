from __future__ import annotations

import base64
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from array import array
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.app.domain.roles import RoleCard


class TTSServiceError(RuntimeError):
    pass


class TTSTextLimitError(TTSServiceError):
    pass


DEFAULT_EMOTION_OPTIONS = [
    "",
    "中性",
    "开心",
    "悲伤",
    "愤怒",
    "害怕",
    "惊讶",
    "温柔",
    "紧张",
    "严肃",
]
DEFAULT_LANGUAGE_OPTIONS = [
    "Auto",
    "Chinese",
    "English",
    "German",
    "Italian",
    "Portuguese",
    "Spanish",
    "Japanese",
    "Korean",
    "French",
    "Russian",
]
DEFAULT_GENERATED_VOICE_TEXT = "这是一段用于试听新音色的语音。"
DEFAULT_TTS_MAX_INPUT_CHARS = 120
DEFAULT_TTS_MAX_NEW_TOKENS = 8192
DEFAULT_TTS_REQUEST_TIMEOUT_SECONDS = 120.0
AUDIO_SUCCESS_STATUSES = {"success", "succeeded", "completed", "done"}


@dataclass(frozen=True)
class VoiceJob:
    voice_job_id: str
    utterance_id: str
    role_id: str
    voice_mode: str
    provider: str
    request_text: str
    reference_audio_path: str | None
    reference_text: str | None
    response_format: str
    output_path: str
    status: str
    error: str | None
    emotion: str = ""
    speed: float = 1.0
    volume: float = 1.0
    language: str = "Auto"
    other_control_text: str | None = None
    x_vector_only: bool = False
    synthesis_segments: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchAudioGenerationReport:
    status: str
    total_count: int
    skipped_count: int
    success_count: int
    failed_count: int
    groups: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    utterances_by_paragraph: dict[str, list[dict[str, Any]]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChapterAudioExportReport:
    status: str
    export_dir: str
    manifest_path: str
    item_count: int
    missing_count: int
    full_audio_path: str | None
    message: str
    full_mp3_path: str | None = None
    package_files: dict[str, str | None] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bounded_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(numeric, minimum), maximum)


def _normalized_language(value: Any, default: str) -> str:
    language = str(value or default).strip()
    return language if language in DEFAULT_LANGUAGE_OPTIONS else default


def _positive_int_from_env(*names: str, default: int) -> int:
    for name in names:
        raw_value = os.environ.get(name, "").strip()
        if not raw_value:
            continue
        try:
            return max(1, int(raw_value))
        except ValueError:
            continue
    return default


def tts_max_input_chars() -> int:
    return _positive_int_from_env(
        "SHUYI_TTS_MAX_INPUT_CHARS",
        "QWEN3_TTS_MAX_INPUT_CHARS",
        default=DEFAULT_TTS_MAX_INPUT_CHARS,
    )


def tts_max_new_tokens() -> int:
    return _positive_int_from_env(
        "SHUYI_TTS_MAX_NEW_TOKENS",
        "QWEN3_TTS_MAX_NEW_TOKENS",
        default=DEFAULT_TTS_MAX_NEW_TOKENS,
    )


def _tts_request_timeout_seconds(text: str) -> float:
    raw_value = os.environ.get("SHUYI_TTS_REQUEST_TIMEOUT_SECONDS", "").strip()
    if raw_value:
        try:
            return max(1.0, float(raw_value))
        except ValueError:
            pass
    return max(DEFAULT_TTS_REQUEST_TIMEOUT_SECONDS, min(480.0, 60.0 + len(text) * 2.0))


def _tts_text_limit_message(text: str, max_chars: int) -> str:
    return (
        f"当前台词文本长度 {len(text)} 字，超过本地 TTS 单条上限 {max_chars} 字；"
        f"已使用最大 max_new_tokens={tts_max_new_tokens()}，未发现可继续安全提高的请求长度参数。"
        "请手动缩短文本或拆成多条音频生成。"
    )


def validate_tts_text_length(text: str) -> None:
    max_chars = tts_max_input_chars()
    if max_chars > 0 and len(text) > max_chars:
        raise TTSTextLimitError(_tts_text_limit_message(text, max_chars))


def _timeout_text_limit_message(text: str, timeout_seconds: float) -> str:
    return (
        f"本地 TTS 生成超时（已等待 {timeout_seconds:.0f} 秒）；当前台词文本长度 {len(text)} 字，"
        f"已使用最大 max_new_tokens={tts_max_new_tokens()}。"
        "模型仍未返回可播放音频，请手动缩短文本或拆成多条音频生成。"
    )


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw_body = exc.read().decode("utf-8", "replace")
    except (OSError, UnicodeDecodeError):
        raw_body = ""
    if not raw_body:
        return "服务未返回错误详情"
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    if detail:
        return json.dumps(detail, ensure_ascii=False)
    return raw_body


def _speed_instruction(speed: float) -> str:
    if speed <= 0.5:
        return "较慢地说"
    if speed < 1.0:
        return "稍慢地说"
    if speed >= 2.0:
        return "很快地说"
    if speed >= 1.5:
        return "较快地说"
    if speed > 1.0:
        return "稍快地说"
    return ""


def _volume_instruction(volume: float) -> str:
    if volume <= 0.5:
        return "小声地说"
    if volume < 1.0:
        return "稍微小声地说"
    if volume >= 1.5:
        return "大声地说"
    if volume > 1.0:
        return "稍微大声地说"
    return ""


def build_control_instruct(
    *, emotion: str, other_control_text: str, speed: float, volume: float
) -> str:
    emotion_map = {
        "中性": "自然地说",
        "开心": "开心地说",
        "悲伤": "悲伤地说",
        "愤怒": "愤怒地说",
        "害怕": "害怕地说",
        "惊讶": "惊讶地说",
        "温柔": "温柔地说",
        "紧张": "紧张地说",
        "严肃": "严肃地说",
    }
    parts: list[str] = []
    emotion_instruction = emotion_map.get(emotion, "")
    if emotion_instruction:
        parts.append(emotion_instruction)
    speed_instruction = _speed_instruction(speed)
    if speed_instruction:
        parts.append(speed_instruction)
    volume_instruction = _volume_instruction(volume)
    if volume_instruction:
        parts.append(volume_instruction)
    if other_control_text:
        parts.append(other_control_text)
    return "；".join(parts)


def model_control_note(voice_mode: str) -> str:
    if voice_mode == "voice_design":
        return "Qwen3-TTS VoiceDesign / Instruct 路径支持中文自然语言控制文本。"
    return "本地 Qwen3-TTS-12Hz-1.7B-Base 声音克隆路径只向模型发送参考音频，以及 reusable_prompt、language 和 x_vector_only 字段；情绪、语速、音量控制提示暂不发送给 Base 模型。"


def build_tts_request(
    utterance: dict[str, Any],
    role: RoleCard,
    *,
    response_format: str = "wav",
    language: str = "Auto",
) -> dict[str, Any]:
    text = (utterance.get("text") or "").strip()
    if not text:
        raise ValueError("配音片段文本不能为空")

    voice_mode = utterance.get("voice_mode") or role.voice_mode
    emotion = str(utterance.get("emotion") or "").strip()
    other_control_text = (
        utterance.get("other_control_text")
        or utterance.get("emotion_control_text")
        or utterance.get("design_prompt")
        or ""
    )
    other_control_text = str(other_control_text).strip()
    language_value = _normalized_language(utterance.get("language"), language)
    x_vector_only = bool(utterance.get("x_vector_only", False))
    speed = _bounded_float(utterance.get("speed"), default=1.0, minimum=0.5, maximum=2.0)
    volume = _bounded_float(utterance.get("volume"), default=1.0, minimum=0.0, maximum=2.0)
    control_instruct = build_control_instruct(
        emotion=emotion,
        other_control_text=other_control_text,
        speed=speed,
        volume=volume,
    )

    if voice_mode == "voice_cloning":
        if not role.reference_audio_path:
            raise ValueError("声音克隆需要参考音频")
        if not role.reference_text:
            raise ValueError("声音克隆需要参考文本")
        payload = {
            "input": text,
            "audio_sample_path": role.reference_audio_path,
            "ref_text": role.reference_text,
            "reusable_prompt": role.reference_text,
            "language": language_value,
            "response_format": response_format,
            "x_vector_only": x_vector_only,
            "emotion": emotion,
            "other_control_text": other_control_text,
            "control_instruct": control_instruct,
            "speed": speed,
            "volume": volume,
        }
        return payload

    if voice_mode == "voice_design":
        design_prompt = other_control_text or utterance.get("design_prompt") or role.design_prompt
        if not design_prompt:
            raise ValueError("声音设计需要音色描述")
        return {
            "input": text,
            "design_prompt": design_prompt,
            "language": language_value,
            "response_format": response_format,
            "emotion": emotion,
            "other_control_text": other_control_text,
            "control_instruct": control_instruct or str(design_prompt),
            "speed": speed,
            "volume": volume,
        }

    raise ValueError(f"不支持的音色模式：{voice_mode}")


def synthesize_local_qwen3(
    request_payload: dict[str, Any],
    *,
    output_path: Path,
    service_base_url: str | None = None,
) -> float:
    if "audio_sample_path" not in request_payload:
        raise TTSServiceError("本地 Qwen3-TTS 当前需要声音克隆参考音频")

    text = str(request_payload["input"])
    validate_tts_text_length(text)

    reference_audio = Path(request_payload["audio_sample_path"])
    if not reference_audio.exists():
        raise TTSServiceError(f"参考音频不存在：{reference_audio}")

    payload = {
        "input": text,
        "audio_sample": base64.b64encode(reference_audio.read_bytes()).decode("ascii"),
        "audio_sample_suffix": _safe_reference_audio_suffix(reference_audio.suffix),
        "ref_text": request_payload["ref_text"],
        "language": request_payload.get("language", "Auto"),
        "response_format": request_payload.get("response_format", "wav"),
        "x_vector_only": bool(request_payload.get("x_vector_only", False)),
        "max_new_tokens": int(request_payload.get("max_new_tokens") or tts_max_new_tokens()),
    }
    base_url = (
        service_base_url or os.environ.get("QWEN3_TTS_BASE_URL") or "http://127.0.0.1:7811"
    ).rstrip("/")
    http_request = urllib.request.Request(
        f"{base_url}/v1/audio/speech",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        timeout_seconds = _tts_request_timeout_seconds(text)
        with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
            audio_bytes = response.read()
    except TTSTextLimitError:
        raise
    except urllib.error.HTTPError as exc:
        detail = _http_error_detail(exc)
        if not detail or detail == "服务未返回错误详情":
            detail = (
                f"{detail}；当前台词文本长度 {len(text)} 字，"
                f"max_new_tokens={tts_max_new_tokens()}，可尝试缩短文本或拆成多条音频生成。"
            )
        raise TTSServiceError(f"本地 Qwen3-TTS 请求失败：HTTP {exc.code}：{detail}") from exc
    except TimeoutError as exc:
        raise TTSTextLimitError(_timeout_text_limit_message(text, timeout_seconds)) from exc
    except Exception as exc:
        raise TTSServiceError(f"本地 Qwen3-TTS 请求失败：{exc}") from exc

    if not audio_bytes:
        raise TTSServiceError("本地 Qwen3-TTS 未返回音频")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio_bytes)
    return validate_wav_duration(output_path)


def tts_synthesis_segments(text: str) -> list[str]:
    """Split only risky short-leading exclamations to avoid TTS swallowing them.

    Qwen3-TTS voice cloning can occasionally skip a very short opening clause when
    the same phrase appears again later in the same utterance, especially for
    shouted dialogue like "放开我！...快放开我！".  Splitting that opening clause
    into its own synthesis request preserves the spoken text while keeping the
    user-facing script and manifest unchanged.
    """

    normalized = _strip_wrapping_dialogue_quotes(text.strip())
    if not normalized:
        return []
    parts = [part for part in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", normalized) if part]
    if len(parts) < 2:
        return [normalized]
    first = parts[0].strip()
    first_core = re.sub(r"[。！？!?；;\s]+$", "", first)
    remainder = "".join(parts[1:]).strip()
    if (
        first.endswith(("！", "!", "？", "?"))
        and 1 <= len(first_core) <= 8
        and first_core in re.sub(r"[\s。！？!?；;，,、]+", "", remainder)
    ):
        return [first, remainder]
    return [normalized]


def synthesize_local_qwen3_guarded(
    request_payload: dict[str, Any],
    *,
    output_path: Path,
    service_base_url: str | None = None,
    synthesize_one: Callable[..., float] = synthesize_local_qwen3,
) -> float:
    segments = tts_synthesis_segments(str(request_payload.get("input") or ""))
    if len(segments) <= 1:
        guarded_payload = {**request_payload, "input": segments[0] if segments else ""}
        return synthesize_one(
            guarded_payload,
            output_path=output_path,
            service_base_url=service_base_url,
        )

    part_paths = [
        output_path.with_name(f"{output_path.stem}-part-{index + 1}{output_path.suffix}")
        for index in range(len(segments))
    ]
    try:
        for segment, part_path in zip(segments, part_paths, strict=True):
            synthesize_one(
                {**request_payload, "input": segment},
                output_path=part_path,
                service_base_url=service_base_url,
            )
        _concatenate_wavs(part_paths, output_path, pause_ms=120)
        return validate_wav_duration(output_path)
    finally:
        for part_path in part_paths:
            try:
                part_path.unlink()
            except OSError:
                pass


def _strip_wrapping_dialogue_quotes(text: str) -> str:
    quote_pairs = {"“": "”", "‘": "’", "\"": "\"", "'": "'"}
    while len(text) >= 2 and text[0] in quote_pairs and text[-1] == quote_pairs[text[0]]:
        text = text[1:-1].strip()
    return text


def synthesize_voice_design_qwen3(
    request_payload: dict[str, Any],
    *,
    output_path: Path,
    service_base_url: str | None = None,
) -> float:
    text = str(request_payload.get("input") or "").strip()
    instruct = str(
        request_payload.get("instruct") or request_payload.get("design_prompt") or ""
    ).strip()
    if not text:
        raise TTSServiceError("声音设计需要输入文本")
    if not instruct:
        raise TTSServiceError("声音设计需要音色描述")

    payload = {
        "input": text,
        "instruct": instruct,
        "language": request_payload.get("language", "Auto"),
        "response_format": request_payload.get("response_format", "wav"),
    }
    base_url = (
        service_base_url or os.environ.get("QWEN3_TTS_BASE_URL") or "http://127.0.0.1:7811"
    ).rstrip("/")
    http_request = urllib.request.Request(
        f"{base_url}/v1/audio/voice-design",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=120) as response:
            audio_bytes = response.read()
    except Exception as exc:
        raise TTSServiceError(f"本地 Qwen3-TTS VoiceDesign 请求失败：{exc}") from exc

    if not audio_bytes:
        raise TTSServiceError("本地 Qwen3-TTS VoiceDesign 未返回音频")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio_bytes)
    return validate_wav_duration(output_path)


def validate_wav_duration(output_path: Path, *, min_duration_seconds: float = 0.5) -> float:
    try:
        with wave.open(str(output_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            frame_rate = wav_file.getframerate()
            duration = frames / float(frame_rate)
    except Exception as exc:
        raise TTSServiceError(f"生成的音频不是可解码的 WAV：{exc}") from exc

    if duration <= min_duration_seconds:
        raise TTSServiceError(
            f"生成音频时长必须大于 {min_duration_seconds} 秒，实际为 {duration:.3f} 秒"
        )
    return duration


def write_silent_wav(
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


def generate_chapter_audio_batch(
    *,
    chapter_id: str,
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    roles: list[RoleCard | dict[str, Any]],
    output_dir: Path,
    synthesize_batch: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
    skip_success: bool = True,
) -> BatchAudioGenerationReport:
    role_by_id = {_role_id(role): role for role in roles}
    pending: list[dict[str, Any]] = []
    skipped_count = 0
    errors: list[dict[str, Any]] = []
    now = _utc_now()

    for order, utterance in enumerate(_iter_utterances(utterances_by_paragraph), start=1):
        text = str(utterance.get("text") or "").strip()
        role_id = _utterance_role_id(utterance)
        if not text or not role_id:
            continue
        if (
            skip_success
            and _is_success_audio_status(utterance.get("audio_status"))
            and utterance.get("audio_path")
        ):
            skipped_count += 1
            continue
        role = role_by_id.get(role_id)
        if role is None:
            utterance.update(audio_status="failed", audio_error=f"角色不存在：{role_id}")
            errors.append(
                {"statement_id": _statement_id(utterance), "message": f"角色不存在：{role_id}"}
            )
            continue
        voice_resource_id = _role_field(role, "voice_resource_id") or role_id
        pending.append(
            {
                "order": order,
                "utterance": utterance,
                "role": role,
                "role_id": role_id,
                "voice_resource_id": voice_resource_id,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    groups: list[dict[str, Any]] = []
    success_count = 0
    failed_count = len(errors)
    synthesize_batch = synthesize_batch or _default_synthesize_batch

    for group_key, group_items in _group_pending_audio(pending).items():
        first = group_items[0]
        role = first["role"]
        request = {
            "chapter_id": chapter_id,
            "role_id": first["role_id"],
            "voice_resource_id": first["voice_resource_id"],
            "reference_audio_path": _role_field(role, "reference_audio_path"),
            "reference_text": _role_field(role, "reference_text"),
            "statement_ids": [_statement_id(item["utterance"]) for item in group_items],
            "texts": [str(item["utterance"].get("text") or "") for item in group_items],
            "languages": [str(item["utterance"].get("language") or "Auto") for item in group_items],
        }
        groups.append(
            {
                "group_key": group_key,
                "voice_resource_id": request["voice_resource_id"],
                "role_id": request["role_id"],
                "count": len(group_items),
            }
        )
        try:
            results = synthesize_batch(request, output_dir=output_dir)
        except TypeError:
            results = synthesize_batch(request)
        except (TTSServiceError, ValueError, RuntimeError, OSError) as exc:
            failed_count += len(group_items)
            for item in group_items:
                utterance = item["utterance"]
                utterance.update(
                    audio_status="failed", audio_error=str(exc), audio_generated_at=now
                )
                errors.append({"statement_id": _statement_id(utterance), "message": str(exc)})
            continue

        result_by_id = {
            str(result.get("statement_id")): result
            for result in results
            if result.get("statement_id")
        }
        for item in group_items:
            utterance = item["utterance"]
            statement_id = _statement_id(utterance)
            result = result_by_id.get(statement_id)
            if result is None or result.get("error"):
                message = str(result.get("error") if result else "batch TTS result missing")
                utterance.update(audio_status="failed", audio_error=message, audio_generated_at=now)
                errors.append({"statement_id": statement_id, "message": message})
                failed_count += 1
                continue
            utterance.update(
                audio_status="success",
                audio_path=str(result.get("audio_path") or ""),
                audio_duration=float(
                    result.get("audio_duration") or result.get("duration_seconds") or 0.0
                ),
                audio_error=None,
                audio_generated_at=now,
                audio_provider=str(result.get("provider") or "local-qwen3-tts"),
                audio_model=str(result.get("model") or "Qwen3-TTS"),
                voice_resource_id=request["voice_resource_id"],
            )
            success_count += 1

    status = "completed" if failed_count == 0 else "completed_with_errors"
    return BatchAudioGenerationReport(
        status=status,
        total_count=success_count + failed_count + skipped_count,
        skipped_count=skipped_count,
        success_count=success_count,
        failed_count=failed_count,
        groups=groups,
        errors=errors,
        utterances_by_paragraph=utterances_by_paragraph,
    )


def export_chapter_audio(
    *,
    chapter_id: str,
    chapter_title: str,
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    roles: list[RoleCard | dict[str, Any]],
    output_dir: Path,
    pause_ms: int = 300,
    speed: float = 1.0,
    trim_silence: bool = False,
    normalize_audio: bool = False,
    target_peak: float = 0.9,
    export_formats: list[str] | None = None,
    mp3_encoder: Callable[[Path, Path], None] | None = None,
) -> ChapterAudioExportReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    role_by_id = {_role_id(role): role for role in roles}
    items: list[dict[str, Any]] = []
    script_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    completed_audio_paths: list[Path] = []
    missing_count = 0
    cursor_seconds = 0.0
    requested_formats = {
        str(item).strip().lower() for item in (export_formats or ["wav"]) if str(item).strip()
    }
    if "mp3" in requested_formats:
        requested_formats.add("wav")

    for index, utterance in enumerate(_iter_utterances(utterances_by_paragraph), start=1):
        text = str(utterance.get("text") or "").strip()
        role_id = _utterance_role_id(utterance)
        if not text:
            continue
        role = role_by_id.get(role_id)
        role_name = str(_role_field(role, "name") or role_id)
        paragraph_id = str(utterance.get("paragraph_id") or f"p-{index:04d}")
        statement_id = _statement_id(utterance)
        filename = _export_audio_filename(chapter_id, paragraph_id, statement_id, role_name)
        source_path = Path(str(utterance.get("audio_path") or ""))
        row_base = {
            "order": len(script_rows) + 1,
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "paragraph_id": paragraph_id,
            "utterance_id": statement_id,
            "role_id": role_id,
            "role_name": role_name,
            "text": text,
        }
        script_rows.append(
            {
                **row_base,
                "audio_status": str(utterance.get("audio_status") or ""),
                "audio_file": filename if source_path else "",
                "start_time": "",
                "end_time": "",
            }
        )
        if (
            source_path
            and _audio_status_allows_export(utterance.get("audio_status"))
            and source_path.exists()
        ):
            target = output_dir / filename
            shutil.copy2(source_path, target)
            completed_audio_paths.append(target)
            duration = float(utterance.get("audio_duration") or validate_wav_duration(target))
            start_time = cursor_seconds
            end_time = cursor_seconds + duration
            cursor_seconds = end_time + max(0, pause_ms) / 1000
            script_rows[-1]["start_time"] = _subtitle_timestamp(start_time, separator=".")
            script_rows[-1]["end_time"] = _subtitle_timestamp(end_time, separator=".")
            items.append(
                {
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                    "statement_id": statement_id,
                    "paragraph_id": paragraph_id,
                    "order": len(items) + 1,
                    "text": text,
                    "role_id": role_id,
                    "role_name": role_name,
                    "voice_resource_id": utterance.get("voice_resource_id")
                    or _role_field(role, "voice_resource_id"),
                    "voice_name": _role_field(role, "voice_description")
                    or _role_field(role, "description"),
                    "filename": filename,
                    "duration": duration,
                    "start_time": start_time,
                    "end_time": end_time,
                    "generated_at": utterance.get("audio_generated_at"),
                }
            )
        else:
            missing_count += 1
            failure_rows.append(
                {
                    **row_base,
                    "audio_status": str(utterance.get("audio_status") or "missing"),
                    "audio_error": str(utterance.get("audio_error") or "音频文件缺失或未生成"),
                }
            )

    role_rows = [_role_export_row(role) for role in roles]
    voice_rows = _voice_export_rows(roles)
    _write_csv(
        output_dir / "script.csv",
        [
            "order",
            "chapter_id",
            "chapter_title",
            "paragraph_id",
            "utterance_id",
            "role_id",
            "role_name",
            "text",
            "audio_status",
            "audio_file",
            "start_time",
            "end_time",
        ],
        script_rows,
    )
    _write_csv(
        output_dir / "roles.csv",
        ["role_id", "role_name", "voice_resource_id", "voice_mode", "description"],
        role_rows,
    )
    _write_csv(
        output_dir / "voices.csv",
        ["voice_resource_id", "voice_name", "reference_audio_path", "reference_text", "voice_mode"],
        voice_rows,
    )
    _write_csv(
        output_dir / "failures.csv",
        [
            "order",
            "chapter_id",
            "chapter_title",
            "paragraph_id",
            "utterance_id",
            "role_id",
            "role_name",
            "text",
            "audio_status",
            "audio_error",
        ],
        failure_rows,
    )
    (output_dir / "subtitles.srt").write_text(_build_srt(items), encoding="utf-8")
    (output_dir / "subtitles.lrc").write_text(_build_lrc(items), encoding="utf-8")

    full_audio_path: str | None = None
    full_mp3_path: str | None = None
    mp3_error: str | None = None
    if missing_count == 0 and completed_audio_paths:
        full_path = output_dir / "chapter_full.wav"
        _concatenate_wavs(
            completed_audio_paths,
            full_path,
            pause_ms=pause_ms,
            trim_silence=trim_silence,
            normalize_audio=normalize_audio,
            target_peak=target_peak,
        )
        full_audio_path = str(full_path)
        if "mp3" in requested_formats:
            mp3_path = output_dir / "chapter_full.mp3"
            try:
                (mp3_encoder or _encode_mp3_with_ffmpeg)(full_path, mp3_path)
            except TTSServiceError as exc:
                mp3_error = str(exc)
            else:
                full_mp3_path = str(mp3_path)

    deliverables: dict[str, str | None] = {
        "full_audio_wav": "chapter_full.wav" if full_audio_path else None,
        "full_audio_mp3": "chapter_full.mp3" if full_mp3_path else None,
        "script_csv": "script.csv",
        "subtitles_srt": "subtitles.srt",
        "subtitles_lrc": "subtitles.lrc",
        "roles_csv": "roles.csv",
        "voices_csv": "voices.csv",
        "failures_csv": "failures.csv",
        "manifest_json": "manifest.json",
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "package_version": "v0.7.1",
                "project_artifact_type": "chapter_delivery_package",
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
                "exported_at": _utc_now(),
                "pause_ms": pause_ms,
                "speed": speed,
                "post_processing": {
                    "pause_ms": pause_ms,
                    "speed": speed,
                    "trim_silence": trim_silence,
                    "normalize_audio": normalize_audio,
                    "target_peak": target_peak,
                },
                "deliverables": deliverables,
                "missing_count": missing_count,
                "failure_count": len(failure_rows),
                "items": items,
                "failures": failure_rows,
                "roles": role_rows,
                "voices": voice_rows,
                **({"mp3_error": mp3_error} if mp3_error else {}),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    message = (
        "导出完成，已包含完整 WAV/MP3 制作包。"
        if full_audio_path
        else f"导出完成；还有 {missing_count} 条台词未完成配音，未生成完整拼接音频。"
    )
    return ChapterAudioExportReport(
        status="completed",
        export_dir=str(output_dir),
        manifest_path=str(manifest_path),
        item_count=len(items),
        missing_count=missing_count,
        full_audio_path=full_audio_path,
        full_mp3_path=full_mp3_path,
        package_files=deliverables,
        message=message,
    )


def _safe_reference_audio_suffix(suffix: str) -> str:
    normalized = suffix.strip().lower()
    if normalized not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
        return ".wav"
    return normalized


def _default_synthesize_batch(request: dict[str, Any], *, output_dir: Path) -> list[dict[str, Any]]:
    output_paths = [
        output_dir / f"{_safe_file_stem(statement_id)}.wav"
        for statement_id in request["statement_ids"]
    ]
    return synthesize_local_qwen3_batch(request, output_paths=output_paths)


def synthesize_local_qwen3_batch(
    request_payload: dict[str, Any],
    *,
    output_paths: list[Path],
    service_base_url: str | None = None,
) -> list[dict[str, Any]]:
    texts = [str(item) for item in request_payload.get("texts") or []]
    if len(texts) != len(output_paths):
        raise TTSServiceError("批量文本数量必须与输出路径数量一致")
    if not texts:
        return []
    for text in texts:
        validate_tts_text_length(text)
    reference_audio_path = str(request_payload.get("reference_audio_path") or "")
    reference_audio = Path(reference_audio_path)
    if not reference_audio.exists():
        raise TTSServiceError(f"参考音频不存在：{reference_audio}")
    payload = {
        "input": texts,
        "audio_sample": base64.b64encode(reference_audio.read_bytes()).decode("ascii"),
        "audio_sample_suffix": _safe_reference_audio_suffix(reference_audio.suffix),
        "ref_text": request_payload.get("reference_text") or "",
        "language": request_payload.get("languages") or ["Auto"] * len(texts),
        "response_format": "wav",
        "x_vector_only": bool(request_payload.get("x_vector_only", False)),
        "max_new_tokens": int(request_payload.get("max_new_tokens") or tts_max_new_tokens()),
    }
    base_url = (
        service_base_url or os.environ.get("QWEN3_TTS_BASE_URL") or "http://127.0.0.1:7811"
    ).rstrip("/")
    http_request = urllib.request.Request(
        f"{base_url}/v1/audio/speech-batch",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        timeout_seconds = max(_tts_request_timeout_seconds(text) for text in texts)
        with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise TTSServiceError(f"本地 Qwen3-TTS 批量请求失败：{exc}") from exc
    audios = response_payload.get("audios") if isinstance(response_payload, dict) else None
    if not isinstance(audios, list) or len(audios) != len(output_paths):
        raise TTSServiceError("本地 Qwen3-TTS 批量响应缺少部分音频")
    results: list[dict[str, Any]] = []
    for statement_id, audio_item, output_path in zip(
        request_payload["statement_ids"], audios, output_paths
    ):
        audio_base64 = audio_item.get("audio_base64") if isinstance(audio_item, dict) else None
        if not audio_base64:
            results.append({"statement_id": statement_id, "error": "empty batch audio"})
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(audio_base64))
        results.append(
            {
                "statement_id": statement_id,
                "audio_path": str(output_path),
                "audio_duration": validate_wav_duration(output_path),
                "provider": "local-qwen3-tts",
                "model": "Qwen3-TTS",
            }
        )
    return results


def _iter_utterances(utterances_by_paragraph: dict[str, list[dict[str, Any]]]):
    for utterances in utterances_by_paragraph.values():
        yield from utterances


def _is_success_audio_status(status: Any) -> bool:
    return str(status or "").strip().lower() in AUDIO_SUCCESS_STATUSES


def _audio_status_allows_export(status: Any) -> bool:
    cleaned = str(status or "").strip().lower()
    if not cleaned:
        return True
    return cleaned in AUDIO_SUCCESS_STATUSES


def _group_pending_audio(pending: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in pending:
        key = str(item["voice_resource_id"] or item["role_id"])
        groups.setdefault(key, []).append(item)
    return groups


def _role_id(role: RoleCard | dict[str, Any]) -> str:
    return str(_role_field(role, "role_id") or "")


def _role_field(role: RoleCard | dict[str, Any] | None, field: str) -> Any:
    if role is None:
        return None
    if isinstance(role, dict):
        return role.get(field)
    return getattr(role, field)


def _utterance_role_id(utterance: dict[str, Any]) -> str:
    return str(utterance.get("speaker_role_id") or utterance.get("role_id") or "")


def _statement_id(utterance: dict[str, Any]) -> str:
    return str(utterance.get("utterance_id") or utterance.get("statement_id") or "")


def _export_audio_filename(
    chapter_id: str, paragraph_id: str, statement_id: str, role_name: str
) -> str:
    chapter_no = _first_number(chapter_id)
    paragraph_no = _first_number(paragraph_id)
    statement_no = _last_number(statement_id)
    safe_role = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", role_name).strip("-") or "role"
    return f"c{chapter_no:04d}_p{paragraph_no:04d}_u{statement_no:04d}_{safe_role}.wav"


def _first_number(value: str) -> int:
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else 1


def _last_number(value: str) -> int:
    matches = re.findall(r"(\d+)", value)
    return int(matches[-1]) if matches else 1


def _safe_file_stem(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value).strip("-") or "audio"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _role_export_row(role: RoleCard | dict[str, Any]) -> dict[str, Any]:
    return {
        "role_id": _role_id(role),
        "role_name": _role_field(role, "name") or _role_id(role),
        "voice_resource_id": _role_field(role, "voice_resource_id") or "",
        "voice_mode": _role_field(role, "voice_mode") or "voice_cloning",
        "description": _role_field(role, "description") or _role_field(role, "profile") or "",
    }


def _voice_export_rows(roles: list[RoleCard | dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role in roles:
        voice_resource_id = str(_role_field(role, "voice_resource_id") or "")
        if not voice_resource_id or voice_resource_id in seen:
            continue
        seen.add(voice_resource_id)
        rows.append(
            {
                "voice_resource_id": voice_resource_id,
                "voice_name": _role_field(role, "voice_description")
                or _role_field(role, "description")
                or voice_resource_id,
                "reference_audio_path": _role_field(role, "reference_audio_path") or "",
                "reference_text": _role_field(role, "reference_text") or "",
                "voice_mode": _role_field(role, "voice_mode") or "voice_cloning",
            }
        )
    return rows


def _subtitle_timestamp(seconds: float, *, separator: str) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _lrc_timestamp(seconds: float) -> str:
    total_cs = max(0, round(seconds * 100))
    minutes, remainder = divmod(total_cs, 6000)
    secs, centis = divmod(remainder, 100)
    return f"{minutes:02d}:{secs:02d}.{centis:02d}"


def _build_srt(items: list[dict[str, Any]]) -> str:
    blocks = []
    for index, item in enumerate(items, start=1):
        start = _subtitle_timestamp(float(item.get("start_time") or 0.0), separator=",")
        end = _subtitle_timestamp(float(item.get("end_time") or 0.0), separator=",")
        blocks.append(f"{index}\n{start} --> {end}\n{item.get('text') or ''}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _build_lrc(items: list[dict[str, Any]]) -> str:
    lines = [
        f"[{_lrc_timestamp(float(item.get('start_time') or 0.0))}]{item.get('text') or ''}"
        for item in items
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def _encode_mp3_with_ffmpeg(source_wav: Path, target_mp3: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TTSServiceError("未找到 ffmpeg，已跳过 MP3 生成")
    completed = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(source_wav), str(target_mp3)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "ffmpeg 转码失败"
        raise TTSServiceError(detail)


def _concatenate_wavs(
    paths: list[Path],
    output_path: Path,
    *,
    pause_ms: int,
    trim_silence: bool = False,
    normalize_audio: bool = False,
    target_peak: float = 0.9,
) -> None:
    first_params = None
    frames: list[bytes] = []
    for path in paths:
        with wave.open(str(path), "rb") as wav_file:
            params = wav_file.getparams()
            if first_params is None:
                first_params = params
            elif (
                params.nchannels != first_params.nchannels
                or params.sampwidth != first_params.sampwidth
                or params.framerate != first_params.framerate
            ):
                raise TTSServiceError(
                    "export requires matching wav channel count, sample width, and sample rate"
                )
            frame_block = wav_file.readframes(wav_file.getnframes())
            if trim_silence:
                frame_block = _trim_silence_frames(frame_block, params)
            if normalize_audio:
                frame_block = _normalize_peak_frames(frame_block, params, target_peak=target_peak)
            frames.append(frame_block)
    if first_params is None:
        return
    pause_frames = int(first_params.framerate * max(0, pause_ms) / 1000)
    pause = b"\x00" * pause_frames * first_params.nchannels * first_params.sampwidth
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(first_params.nchannels)
        output.setsampwidth(first_params.sampwidth)
        output.setframerate(first_params.framerate)
        for index, frame_block in enumerate(frames):
            if index:
                output.writeframes(pause)
            output.writeframes(frame_block)


def _trim_silence_frames(frame_block: bytes, params: wave._wave_params) -> bytes:
    if params.sampwidth != 2 or not frame_block:
        return frame_block
    samples = array("h")
    samples.frombytes(frame_block)
    if sys.byteorder != "little":
        samples.byteswap()
    threshold = 128
    start = 0
    end = len(samples)
    while start < end and abs(samples[start]) <= threshold:
        start += params.nchannels
    while end > start and abs(samples[end - 1]) <= threshold:
        end -= params.nchannels
    if start >= end:
        return frame_block
    trimmed = array("h", samples[start:end])
    if sys.byteorder != "little":
        trimmed.byteswap()
    return trimmed.tobytes()


def _normalize_peak_frames(
    frame_block: bytes, params: wave._wave_params, *, target_peak: float
) -> bytes:
    if params.sampwidth != 2 or not frame_block:
        return frame_block
    samples = array("h")
    samples.frombytes(frame_block)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max((abs(sample) for sample in samples), default=0)
    if peak == 0:
        return frame_block
    target = int(32767 * min(max(target_peak, 0.1), 1.0))
    gain = target / peak
    normalized = array("h", (max(-32768, min(32767, int(sample * gain))) for sample in samples))
    if sys.byteorder != "little":
        normalized.byteswap()
    return normalized.tobytes()


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()
