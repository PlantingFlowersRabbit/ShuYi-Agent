#!/bin/sh
set -eu

export SHUYI_DEVICE="${SHUYI_DEVICE:-auto}"
export SHUYI_MODEL_DIR="${SHUYI_MODEL_DIR:-/models}"
export SHUYI_DATA_DIR="${SHUYI_DATA_DIR:-/data}"
export SHUYI_MODEL_AUTO_DOWNLOAD="${SHUYI_MODEL_AUTO_DOWNLOAD:-0}"
export QWEN3_TTS_DEVICE="${QWEN3_TTS_DEVICE:-$SHUYI_DEVICE}"
export QWEN3_TTS_MODEL_PATH="${QWEN3_TTS_MODEL_PATH:-$SHUYI_MODEL_DIR/Qwen3-TTS-12Hz-1.7B-Base}"
export QWEN3_TTS_VOICE_DESIGN_MODEL_PATH="${QWEN3_TTS_VOICE_DESIGN_MODEL_PATH:-$SHUYI_MODEL_DIR/Qwen3-TTS-12Hz-1.7B-VoiceDesign}"

mkdir -p "$SHUYI_DATA_DIR" "$SHUYI_MODEL_DIR"
python /app/scripts/container/download_models.py
exec python /app/scripts/container/supervise.py "$@"
