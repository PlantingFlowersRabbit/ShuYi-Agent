#!/usr/bin/env python3
import argparse
import asyncio
import base64
import os
import tempfile
from pathlib import Path

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from qwen_tts import Qwen3TTSModel

app = FastAPI(title="NovelVoice Qwen3-TTS Server")
model = None


def load_model(model_path: str):
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


@app.on_event("startup")
async def startup():
    global model
    model_path = os.environ["QWEN3_TTS_MODEL_PATH"]
    model = await asyncio.to_thread(load_model, model_path)


@app.get("/health")
async def health():
    return {"ok": model is not None}


@app.post("/v1/audio/speech/upload")
async def speech_upload(
    input: str = Form(...),
    voice_file: UploadFile = File(...),  # noqa: B008
    ref_text: str = Form(""),
    language: str = Form("Chinese"),
    response_format: str = Form("wav"),
    x_vector_only: bool = Form(False),
):
    suffix = Path(voice_file.filename or "reference.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as reference:
        reference.write(await voice_file.read())
        reference_path = reference.name

    try:
        wavs, sr = await asyncio.to_thread(
            model.generate_voice_clone,
            text=input,
            language=language,
            ref_audio=reference_path,
            ref_text=ref_text,
            x_vector_only_mode=x_vector_only,
        )
        return encode_audio_response(wavs[0], sr, response_format)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            os.remove(reference_path)
        except OSError:
            pass


@app.post("/v1/audio/speech")
async def speech_json(payload: dict):
    text = payload.get("input", "")
    ref_text = payload.get("ref_text") or payload.get("audio_sample_text") or ""
    language = payload.get("language", "Chinese")
    response_format = payload.get("response_format", "wav")
    x_vector_only = bool(payload.get("x_vector_only", False))
    audio_sample = payload.get("audio_sample") or payload.get("voice_file")
    if not text or not audio_sample:
        raise HTTPException(status_code=400, detail="input and audio_sample are required")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as reference:
        reference.write(base64.b64decode(audio_sample))
        reference_path = reference.name

    try:
        wavs, sr = await asyncio.to_thread(
            model.generate_voice_clone,
            text=text,
            language=language,
            ref_audio=reference_path,
            ref_text=ref_text,
            x_vector_only_mode=x_vector_only,
        )
        return encode_audio_response(wavs[0], sr, response_format)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            os.remove(reference_path)
        except OSError:
            pass


@app.post("/v1/audio/voice-design")
async def voice_design_json(payload: dict):
    text = payload.get("input", "")
    instruct = payload.get("instruct") or payload.get("design_prompt") or ""
    language = payload.get("language", "Chinese")
    response_format = payload.get("response_format", "wav")
    if not text or not instruct:
        raise HTTPException(status_code=400, detail="input and instruct are required")

    try:
        wavs, sr = await asyncio.to_thread(
            model.generate_voice_design,
            text=text,
            language=language,
            instruct=instruct,
        )
        return encode_audio_response(wavs[0], sr, response_format)
    except AttributeError as exc:
        raise HTTPException(
            status_code=501,
            detail="loaded Qwen3-TTS model does not provide generate_voice_design; use Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def encode_audio_response(wav, sr, response_format: str) -> Response:
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7811)
    parser.add_argument(
        "--device",
        default=os.environ.get("QWEN3_TTS_DEVICE", "cpu"),
        choices=["cpu", "mps"],
    )
    args = parser.parse_args()

    os.environ["QWEN3_TTS_MODEL_PATH"] = args.model_path
    os.environ["QWEN3_TTS_DEVICE"] = args.device
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
