from __future__ import annotations

import base64
import json
import os
import urllib.request
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.app.domain.roles import RoleCard


class TTSServiceError(RuntimeError):
    pass


DEFAULT_EMOTION_OPTIONS = ["", "中性", "开心", "悲伤", "愤怒", "害怕", "惊讶", "温柔", "紧张", "严肃"]
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


def build_control_instruct(*, emotion: str, other_control_text: str, speed: float, volume: float) -> str:
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
    return "本地 Qwen3-TTS-12Hz-1.7B-Base voice cloning 路径只向模型发送参考音频、reusable prompt、language 和 x_vector_only；情绪、语速、音量控制提示暂不发送给 Base 模型。"


def build_tts_request(
    utterance: dict[str, Any],
    role: RoleCard,
    *,
    response_format: str = "wav",
    language: str = "Auto",
) -> dict[str, Any]:
    text = (utterance.get("text") or "").strip()
    if not text:
        raise ValueError("utterance text is required")

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
            raise ValueError("voice cloning requires reference audio")
        if not role.reference_text:
            raise ValueError("voice cloning requires reference text")
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
            raise ValueError("voice design requires design prompt")
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

    raise ValueError(f"Unsupported voice mode: {voice_mode}")


def synthesize_local_qwen3(
    request_payload: dict[str, Any],
    *,
    output_path: Path,
    service_base_url: str | None = None,
) -> float:
    if "audio_sample_path" not in request_payload:
        raise TTSServiceError("local Qwen3-TTS currently requires voice cloning reference audio")

    reference_audio = Path(request_payload["audio_sample_path"])
    if not reference_audio.exists():
        raise TTSServiceError(f"reference audio does not exist: {reference_audio}")

    payload = {
        "input": request_payload["input"],
        "audio_sample": base64.b64encode(reference_audio.read_bytes()).decode("ascii"),
        "ref_text": request_payload["ref_text"],
        "language": request_payload.get("language", "Auto"),
        "response_format": request_payload.get("response_format", "wav"),
        "x_vector_only": bool(request_payload.get("x_vector_only", False)),
    }
    base_url = (service_base_url or os.environ.get("QWEN3_TTS_BASE_URL") or "http://127.0.0.1:7811").rstrip(
        "/"
    )
    http_request = urllib.request.Request(
        f"{base_url}/v1/audio/speech",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=120) as response:
            audio_bytes = response.read()
    except Exception as exc:
        raise TTSServiceError(f"local Qwen3-TTS request failed: {exc}") from exc

    if not audio_bytes:
        raise TTSServiceError("local Qwen3-TTS returned empty audio")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio_bytes)
    return validate_wav_duration(output_path)


def synthesize_voice_design_qwen3(
    request_payload: dict[str, Any],
    *,
    output_path: Path,
    service_base_url: str | None = None,
) -> float:
    text = str(request_payload.get("input") or "").strip()
    instruct = str(request_payload.get("instruct") or request_payload.get("design_prompt") or "").strip()
    if not text:
        raise TTSServiceError("voice design requires input text")
    if not instruct:
        raise TTSServiceError("voice design requires instruct description")

    payload = {
        "input": text,
        "instruct": instruct,
        "language": request_payload.get("language", "Auto"),
        "response_format": request_payload.get("response_format", "wav"),
    }
    base_url = (service_base_url or os.environ.get("QWEN3_TTS_BASE_URL") or "http://127.0.0.1:7811").rstrip(
        "/"
    )
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
        raise TTSServiceError(f"local Qwen3-TTS VoiceDesign request failed: {exc}") from exc

    if not audio_bytes:
        raise TTSServiceError("local Qwen3-TTS VoiceDesign returned empty audio")
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
        raise TTSServiceError(f"generated audio is not a decodable wav: {exc}") from exc

    if duration <= min_duration_seconds:
        raise TTSServiceError(
            f"generated audio duration must be > {min_duration_seconds}s, got {duration:.3f}s"
        )
    return duration
