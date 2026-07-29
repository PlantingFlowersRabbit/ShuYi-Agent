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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_tts_request(
    utterance: dict[str, Any],
    role: RoleCard,
    *,
    response_format: str = "wav",
    language: str = "Chinese",
) -> dict[str, Any]:
    text = (utterance.get("text") or "").strip()
    if not text:
        raise ValueError("utterance text is required")

    voice_mode = utterance.get("voice_mode") or role.voice_mode
    emotion_control_text = (utterance.get("design_prompt") or utterance.get("emotion_control_text") or "").strip()
    if voice_mode == "voice_cloning":
        if not role.reference_audio_path:
            raise ValueError("voice cloning requires reference audio")
        if not role.reference_text:
            raise ValueError("voice cloning requires reference text")
        payload = {
            "input": text,
            "audio_sample_path": role.reference_audio_path,
            "ref_text": role.reference_text,
            "language": language,
            "response_format": response_format,
            "x_vector_only": False,
        }
        if emotion_control_text:
            payload["emotion_control_text"] = emotion_control_text
        return payload

    if voice_mode == "voice_design":
        design_prompt = utterance.get("design_prompt") or role.design_prompt
        if not design_prompt:
            raise ValueError("voice design requires design prompt")
        return {
            "input": text,
            "design_prompt": design_prompt,
            "language": language,
            "response_format": response_format,
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
        "language": request_payload.get("language", "Chinese"),
        "response_format": request_payload.get("response_format", "wav"),
        "x_vector_only": bool(request_payload.get("x_vector_only", False)),
    }
    if request_payload.get("emotion_control_text"):
        payload["emotion_control_text"] = request_payload["emotion_control_text"]
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
