#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

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

export SHUYI_MODEL_AUTO_DOWNLOAD="${SHUYI_MODEL_AUTO_DOWNLOAD:-1}"
docker compose -f compose.cuda.yaml up --build
