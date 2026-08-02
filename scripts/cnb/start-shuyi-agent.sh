#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

: "${SHUYI_HOST_PORT:=8000}"
export SHUYI_HOST_PORT

default_cors_origins="http://127.0.0.1:5173,http://localhost:5173,https://plantingflowersrabbit.github.io"
default_cors_origin_regex='https://.*\.cnb\.run'

if [ -z "${SHUYI_CORS_ORIGINS:-}" ] && ! { [ -f .env ] && grep -Eq '^[[:space:]]*SHUYI_CORS_ORIGINS[[:space:]]*=' .env; }; then
  export SHUYI_CORS_ORIGINS="$default_cors_origins"
fi

if [ -z "${SHUYI_CORS_ORIGIN_REGEX:-}" ] && ! { [ -f .env ] && grep -Eq '^[[:space:]]*SHUYI_CORS_ORIGIN_REGEX[[:space:]]*=' .env; }; then
  export SHUYI_CORS_ORIGIN_REGEX="$default_cors_origin_regex"
fi

echo "=================================================="
echo "  ShuYi-Agent CNB backend launcher"
echo "=================================================="

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 docker，无法启动容器化后端。"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "未找到 docker compose，无法启动 compose.cuda.yaml。"
  exit 1
fi

echo "后端本地访问地址：http://localhost:${SHUYI_HOST_PORT}"
echo "后端公网访问地址以 VS Code PORTS 面板显示的 Forwarded Address 为准。"
echo "GitHub Pages 的后端 API 可填写：<PORTS 面板 Forwarded Address>/api/v1"
echo "容器内 FastAPI 端口为 8000；CNB 工作区对外预览端口为 ${SHUYI_HOST_PORT}。"
echo "浏览器 CORS 允许来源：${SHUYI_CORS_ORIGINS:-使用 .env 中的 SHUYI_CORS_ORIGINS}"
echo "浏览器 CORS 来源正则：${SHUYI_CORS_ORIGIN_REGEX:-使用 .env 中的 SHUYI_CORS_ORIGIN_REGEX}"
echo "TTS 模型默认由前端“模型配置 > 下载并部署”按钮后台下载和启动。"

if [ "${SHUYI_CNB_LAUNCH_DRY_RUN:-0}" = "1" ]; then
  echo "SHUYI_CNB_LAUNCH_DRY_RUN=1，跳过 docker compose 启动。"
  exit 0
fi

export SHUYI_MODEL_AUTO_DOWNLOAD="${SHUYI_MODEL_AUTO_DOWNLOAD:-0}"
docker compose -f compose.cuda.yaml down --remove-orphans || true
docker compose -f compose.cuda.yaml up --build
