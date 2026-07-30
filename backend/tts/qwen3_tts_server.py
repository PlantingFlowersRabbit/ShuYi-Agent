#!/usr/bin/env python3
import argparse
import asyncio
import base64
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

try:
    import soundfile as sf
except ImportError:  # pragma: no cover - runtime dependency for the local TTS service.
    sf = None

try:
    import torch
except ImportError:  # pragma: no cover - runtime dependency for the local TTS service.
    torch = None

try:
    from qwen_tts import Qwen3TTSModel
except ImportError:  # pragma: no cover - runtime dependency for the local TTS service.
    Qwen3TTSModel = None

app = FastAPI(title="NovelVoice Qwen3-TTS Server")
voice_clone_model = None
voice_design_model = None
voice_clone_prompt_cache: dict[str, Any] = {}
REFERENCE_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
DEFAULT_TTS_MAX_INPUT_CHARS = 120
DEFAULT_TTS_MAX_NEW_TOKENS = 8192


def positive_int_from_env(*names: str, default: int) -> int:
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
    return positive_int_from_env(
        "NOVELVOICE_TTS_MAX_INPUT_CHARS",
        "QWEN3_TTS_MAX_INPUT_CHARS",
        default=DEFAULT_TTS_MAX_INPUT_CHARS,
    )


def tts_max_new_tokens(value: Any = None) -> int:
    try:
        if value is not None:
            return max(1, int(value))
    except (TypeError, ValueError):
        pass
    return positive_int_from_env(
        "NOVELVOICE_TTS_MAX_NEW_TOKENS",
        "QWEN3_TTS_MAX_NEW_TOKENS",
        default=DEFAULT_TTS_MAX_NEW_TOKENS,
    )


def validate_request_text(text: str) -> None:
    max_chars = tts_max_input_chars()
    if max_chars > 0 and len(text) > max_chars:
        raise HTTPException(
            status_code=422,
            detail=(
                f"当前语句文本长度 {len(text)} 字，超过本地 TTS 单条上限 {max_chars} 字；"
                f"已使用最大 max_new_tokens={tts_max_new_tokens()}，未发现可继续安全提高的请求长度参数。"
                "请手动缩短文本或拆成多条音频生成。"
            ),
        )


def exception_detail(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def load_model(model_path: str):
    if torch is None or Qwen3TTSModel is None:
        raise RuntimeError("qwen_tts and torch are required to start the local Qwen3-TTS service")
    device_map = os.environ.get("QWEN3_TTS_DEVICE", "cpu").strip().lower() or "cpu"
    if device_map not in {"cpu", "mps"}:
        device_map = "cpu"

    dtype = torch.float32
    if device_map == "mps":
        dtype = torch.float16

    print(f"Loading Qwen3-TTS from {model_path}", flush=True)
    print(f"Using device={device_map}, dtype={dtype}", flush=True)
    return Qwen3TTSModel.from_pretrained(
        model_path,
        device_map=device_map,
        dtype=dtype,
    )


def _voice_clone_prompt_cache_key(reference_audio: bytes, reusable_prompt: str, x_vector_only: bool) -> str:
    digest = hashlib.sha256()
    digest.update(reference_audio)
    digest.update(b"\0")
    digest.update(reusable_prompt.encode("utf-8"))
    digest.update(b"\0")
    digest.update(b"1" if x_vector_only else b"0")
    return digest.hexdigest()


def get_or_create_voice_clone_prompt(
    model,
    *,
    reference_path: str,
    reference_audio: bytes,
    reusable_prompt: str,
    x_vector_only: bool,
):
    if not hasattr(model, "create_voice_clone_prompt"):
        return None
    cache_key = _voice_clone_prompt_cache_key(reference_audio, reusable_prompt, x_vector_only)
    if cache_key not in voice_clone_prompt_cache:
        voice_clone_prompt_cache[cache_key] = create_voice_clone_prompt(
            model,
            reference_path=reference_path,
            reusable_prompt=reusable_prompt,
            x_vector_only=x_vector_only,
        )
    return voice_clone_prompt_cache[cache_key]


def create_voice_clone_prompt(model, *, reference_path: str, reusable_prompt: str, x_vector_only: bool):
    try:
        return model.create_voice_clone_prompt(
            ref_audio=reference_path,
            ref_text=reusable_prompt,
            x_vector_only_mode=x_vector_only,
        )
    except TypeError as exc:
        if "x_vector_only_mode" not in str(exc):
            raise
        return model.create_voice_clone_prompt(
            ref_audio=reference_path,
            ref_text=reusable_prompt,
            x_vector_only=x_vector_only,
        )


def generate_voice_clone_with_reusable_prompt(
    model,
    *,
    text: str,
    language: str,
    reference_path: str,
    reference_audio: bytes,
    reusable_prompt: str,
    x_vector_only: bool,
    max_new_tokens: int = DEFAULT_TTS_MAX_NEW_TOKENS,
):
    voice_clone_prompt = get_or_create_voice_clone_prompt(
        model,
        reference_path=reference_path,
        reference_audio=reference_audio,
        reusable_prompt=reusable_prompt,
        x_vector_only=x_vector_only,
    )
    kwargs: dict[str, Any] = {"text": text, "language": language}
    if voice_clone_prompt is None:
        kwargs.update(
            ref_audio=reference_path,
            ref_text=reusable_prompt,
            x_vector_only_mode=x_vector_only,
        )
    else:
        kwargs["voice_clone_prompt"] = voice_clone_prompt
    kwargs["max_new_tokens"] = max_new_tokens
    return model.generate_voice_clone(**kwargs)


@app.on_event("startup")
async def startup():
    global voice_clone_model, voice_design_model
    model_path = os.environ["QWEN3_TTS_MODEL_PATH"]
    voice_clone_model = await asyncio.to_thread(load_model, model_path)

    design_model_path = os.environ.get("QWEN3_TTS_VOICE_DESIGN_MODEL_PATH", "").strip()
    if design_model_path and design_model_path != model_path:
        voice_design_model = await asyncio.to_thread(load_model, design_model_path)
    else:
        voice_design_model = voice_clone_model


@app.get("/health")
async def health():
    voice_clone_ready = voice_clone_model is not None
    voice_design_loaded = voice_design_model is not None
    voice_design_capable = voice_design_loaded and hasattr(voice_design_model, "generate_voice_design")
    return {
        "ok": voice_clone_ready and voice_design_capable,
        "voice_clone": voice_clone_ready,
        "voice_design": voice_design_loaded,
        "voice_design_capable": voice_design_capable,
    }


@app.post("/v1/audio/speech/upload")
async def speech_upload(
    input: str = Form(...),
    voice_file: UploadFile = File(...),  # noqa: B008
    ref_text: str = Form(""),
    language: str = Form("Auto"),
    response_format: str = Form("wav"),
    x_vector_only: bool = Form(False),
    max_new_tokens: int | None = Form(None),
):
    validate_request_text(input)
    suffix = Path(voice_file.filename or "reference.wav").suffix or ".wav"
    reference_audio = await voice_file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as reference:
        reference.write(reference_audio)
        reference_path = reference.name

    try:
        wavs, sr = await asyncio.to_thread(
            generate_voice_clone_with_reusable_prompt,
            voice_clone_model,
            text=input,
            language=language,
            reference_path=reference_path,
            reference_audio=reference_audio,
            reusable_prompt=ref_text,
            x_vector_only=x_vector_only,
            max_new_tokens=tts_max_new_tokens(max_new_tokens),
        )
        return encode_audio_response(wavs[0], sr, response_format)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=exception_detail(exc)) from exc
    finally:
        try:
            os.remove(reference_path)
        except OSError:
            pass


@app.post("/v1/audio/speech")
async def speech_json(payload: dict):
    text = payload.get("input", "")
    ref_text = payload.get("ref_text") or payload.get("audio_sample_text") or ""
    language = payload.get("language", "Auto")
    response_format = payload.get("response_format", "wav")
    x_vector_only = bool(payload.get("x_vector_only", False))
    max_new_tokens = tts_max_new_tokens(payload.get("max_new_tokens"))
    audio_sample = payload.get("audio_sample") or payload.get("voice_file")
    if not text or not audio_sample:
        raise HTTPException(status_code=400, detail="input and audio_sample are required")
    validate_request_text(text)

    reference_audio = base64.b64decode(audio_sample)
    suffix = safe_reference_audio_suffix(payload.get("audio_sample_suffix") or payload.get("audio_sample_format"))
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as reference:
        reference.write(reference_audio)
        reference_path = reference.name

    try:
        wavs, sr = await asyncio.to_thread(
            generate_voice_clone_with_reusable_prompt,
            voice_clone_model,
            text=text,
            language=language,
            reference_path=reference_path,
            reference_audio=reference_audio,
            reusable_prompt=ref_text,
            x_vector_only=x_vector_only,
            max_new_tokens=max_new_tokens,
        )
        return encode_audio_response(wavs[0], sr, response_format)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=exception_detail(exc)) from exc
    finally:
        try:
            os.remove(reference_path)
        except OSError:
            pass


def safe_reference_audio_suffix(value: Any) -> str:
    suffix = str(value or "").strip().lower()
    if not suffix.startswith("."):
        suffix = Path(f"reference.{suffix}").suffix.lower()
    if suffix not in REFERENCE_AUDIO_SUFFIXES:
        return ".wav"
    return suffix


@app.post("/v1/audio/voice-design")
async def voice_design_json(payload: dict):
    text = payload.get("input", "")
    instruct = payload.get("instruct") or payload.get("design_prompt") or ""
    language = payload.get("language", "Auto")
    response_format = payload.get("response_format", "wav")
    max_new_tokens = tts_max_new_tokens(payload.get("max_new_tokens"))
    if not text or not instruct:
        raise HTTPException(status_code=400, detail="input and instruct are required")
    validate_request_text(text)

    try:
        wavs, sr = await asyncio.to_thread(
            voice_design_model.generate_voice_design,
            text=text,
            language=language,
            instruct=instruct,
            max_new_tokens=max_new_tokens,
        )
        return encode_audio_response(wavs[0], sr, response_format)
    except AttributeError as exc:
        raise HTTPException(
            status_code=501,
            detail="loaded Qwen3-TTS model does not provide generate_voice_design; use Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=exception_detail(exc)) from exc


def encode_audio_response(wav, sr, response_format: str) -> Response:
    if sf is None:
        raise HTTPException(status_code=500, detail="soundfile is required to encode Qwen3-TTS audio")
    fmt = response_format.lower()
    if fmt not in {"wav", "flac", "ogg"}:
        fmt = "wav"

    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as output:
        output_path = output.name

    try:
        sf.write(output_path, wav, sr, format=fmt.upper())
        data = Path(output_path).read_bytes()
    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass

    media_type = {
        "wav": "audio/wav",
        "flac": "audio/flac",
        "ogg": "audio/ogg",
    }[fmt]
    return Response(content=data, media_type=media_type)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--voice-design-model-path", default=os.environ.get("QWEN3_TTS_VOICE_DESIGN_MODEL_PATH", ""))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7811)
    parser.add_argument(
        "--device",
        default=os.environ.get("QWEN3_TTS_DEVICE", "cpu"),
        choices=["cpu", "mps"],
    )
    args = parser.parse_args()

    os.environ["QWEN3_TTS_MODEL_PATH"] = args.model_path
    if args.voice_design_model_path:
        os.environ["QWEN3_TTS_VOICE_DESIGN_MODEL_PATH"] = args.voice_design_model_path
    os.environ["QWEN3_TTS_DEVICE"] = args.device
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
