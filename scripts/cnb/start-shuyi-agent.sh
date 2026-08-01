#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

: "${SHUYI_HOST_PORT:=8000}"
export SHUYI_HOST_PORT

proxy_template="${CNB_VSCODE_PROXY_URI:-}"
backend_public_url=""
if [ -n "$proxy_template" ]; then
  backend_public_url="${proxy_template//\{\{port\}\}/$SHUYI_HOST_PORT}"
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

if [ -n "$backend_public_url" ]; then
  echo "后端公网访问地址：$backend_public_url"
  echo "GitHub Pages 的 VITE_API_BASE_URL 可填写：${backend_public_url%/}/api/v1"
else
  echo "后端已映射到工作区端口 ${SHUYI_HOST_PORT}；公网地址请在 VS Code PORTS 面板查看。"
  echo "GitHub Pages 的 VITE_API_BASE_URL 可填写：<PORTS 面板公网地址>/api/v1"
fi
echo "容器内 FastAPI 端口为 8000；CNB 工作区对外预览端口为 ${SHUYI_HOST_PORT}。"
echo "TTS 模型默认由前端“模型配置 > 下载并部署”按钮后台下载和启动。"

if [ "${SHUYI_CNB_LAUNCH_DRY_RUN:-0}" = "1" ]; then
  echo "SHUYI_CNB_LAUNCH_DRY_RUN=1，跳过 docker compose 启动。"
  exit 0
fi

export SHUYI_MODEL_AUTO_DOWNLOAD="${SHUYI_MODEL_AUTO_DOWNLOAD:-0}"
docker compose -f compose.cuda.yaml down --remove-orphans || true
docker compose -f compose.cuda.yaml up --build
