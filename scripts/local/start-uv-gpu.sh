#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYPI_INDEX_URL="${PYPI_INDEX_URL:-http://mirrors.aliyun.com/pypi/simple}"
PYPI_TRUSTED_HOST="${PYPI_TRUSTED_HOST:-mirrors.aliyun.com}"
NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"
TORCH_BACKEND="${TORCH_BACKEND:-cu128}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv-gpu}"
APT_PACKAGES=(ffmpeg libsndfile1 sox)
UV_INDEX_ARGS=(--default-index "$PYPI_INDEX_URL" --allow-insecure-host "$PYPI_TRUSTED_HOST")

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令：$1" >&2
    return 1
  fi
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :$port )" | awk 'NR > 1 { found = 1 } END { exit !found }'
  else
    return 1
  fi
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  echo "未检测到 uv，使用镜像源安装 uv..."
  "$PYTHON_BIN" -m pip install \
    -i "$PYPI_INDEX_URL" \
    --trusted-host "$PYPI_TRUSTED_HOST" \
    uv
}

install_system_packages() {
  if [[ "${SKIP_APT:-0}" == "1" ]]; then
    echo "已跳过系统依赖安装：SKIP_APT=1"
    return
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "未检测到 apt-get，请手动安装：${APT_PACKAGES[*]}" >&2
    return
  fi

  local missing=()
  command -v ffmpeg >/dev/null 2>&1 || missing+=(ffmpeg)
  command -v sox >/dev/null 2>&1 || missing+=(sox)
  ldconfig -p 2>/dev/null | grep -q 'libsndfile' || missing+=(libsndfile1)

  if (( ${#missing[@]} == 0 )); then
    return
  fi

  echo "安装系统音频依赖：${missing[*]}"
  if [[ "$(id -u)" == "0" ]]; then
    apt-get update
    apt-get install -y "${APT_PACKAGES[@]}"
  elif command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y "${APT_PACKAGES[@]}"
  else
    echo "当前用户非 root 且无 sudo，请手动安装：${APT_PACKAGES[*]}" >&2
    exit 1
  fi
}

install_python_packages() {
  echo "创建或复用 $VENV_DIR..."
  uv venv "$VENV_DIR" --allow-existing --python "$PYTHON_BIN" --link-mode copy "${UV_INDEX_ARGS[@]}"

  echo "安装后端依赖..."
  UV_LINK_MODE=copy uv pip install --python "$VENV_DIR/bin/python" --project "$ROOT_DIR" \
    --group backend "${UV_INDEX_ARGS[@]}"

  echo "安装模型下载与上传运行依赖..."
  UV_LINK_MODE=copy uv pip install --python "$VENV_DIR/bin/python" \
    python-multipart huggingface-hub modelscope soundfile \
    "${UV_INDEX_ARGS[@]}"

  echo "安装 GPU 版 PyTorch 与 Qwen-TTS：$TORCH_BACKEND"
  UV_LINK_MODE=copy uv pip install --python "$VENV_DIR/bin/python" \
    torch qwen-tts \
    --torch-backend "$TORCH_BACKEND" \
    "${UV_INDEX_ARGS[@]}"
}

verify_gpu() {
  "$VENV_DIR/bin/python" - <<'PY'
import sys
import torch

if not torch.cuda.is_available():
    print("未检测到可用 CUDA，请确认 NVIDIA 驱动可用，并尝试 TORCH_BACKEND=cu128/其他后端。", file=sys.stderr)
    raise SystemExit(1)

print(f"CUDA 可用：{torch.cuda.get_device_name(0)}")
PY
}

install_frontend_packages() {
  need_cmd npm
  echo "安装前端依赖..."
  npm --prefix frontend ci --registry "$NPM_REGISTRY"
}

prepare_env() {
  if [[ ! -f .env && -f .env.example ]]; then
    cp .env.example .env
  fi
  mkdir -p data models outputs
}

start_services() {
  if port_in_use "$BACKEND_PORT"; then
    echo "端口 $BACKEND_PORT 已被占用，请先停止已有后端服务。" >&2
    exit 1
  fi
  if port_in_use "$FRONTEND_PORT"; then
    echo "端口 $FRONTEND_PORT 已被占用，请先停止已有前端服务。" >&2
    exit 1
  fi

  echo "启动后端：http://$BACKEND_HOST:$BACKEND_PORT"
  SHUYI_DATA_DIR="${SHUYI_DATA_DIR:-$ROOT_DIR/data}" \
  SHUYI_DEVICE=cuda QWEN3_TTS_DEVICE=cuda \
    "$VENV_DIR/bin/python" -m uvicorn backend.app.api.app:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" &
  backend_pid=$!

  echo "启动前端：http://$FRONTEND_HOST:$FRONTEND_PORT"
  VITE_API_BASE_URL="${VITE_API_BASE_URL:-/api/v1}" \
    npm --prefix frontend run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
  frontend_pid=$!

  stop_services() {
    kill "$backend_pid" "$frontend_pid" >/dev/null 2>&1 || true
    wait "$backend_pid" "$frontend_pid" 2>/dev/null || true
  }
  trap stop_services EXIT INT TERM

  echo "书弈 Agent GPU 模式已启动。按 Ctrl-C 停止。"
  wait -n "$backend_pid" "$frontend_pid"
}

main() {
  need_cmd "$PYTHON_BIN"
  need_cmd nvidia-smi
  install_uv
  install_system_packages
  prepare_env
  install_python_packages
  verify_gpu
  install_frontend_packages
  start_services
}

main "$@"
