#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

: "${SHUYI_HOST_PORT:=8000}"
export SHUYI_HOST_PORT

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

if [ -z "${SHUYI_API_TOKEN:-}" ]; then
  token_file="${SHUYI_API_TOKEN_FILE:-$ROOT_DIR/.shuyi-api-token}"
  if [ -s "$token_file" ]; then
    SHUYI_API_TOKEN="$(tr -d '\r\n' < "$token_file")"
  else
    umask 077
    if command -v openssl >/dev/null 2>&1; then
      SHUYI_API_TOKEN="$(openssl rand -hex 32)"
    else
      SHUYI_API_TOKEN="$(python3 - <<'PY'
import secrets

print(secrets.token_urlsafe(48))
PY
)"
    fi
    printf '%s\n' "$SHUYI_API_TOKEN" > "$token_file"
  fi
  export SHUYI_API_TOKEN
  echo "后端访问令牌（自动生成，已写入 .shuyi-api-token）："
  echo "$SHUYI_API_TOKEN"
  token_hint="上方自动生成的后端访问令牌"
else
  export SHUYI_API_TOKEN
  echo "已使用环境变量 SHUYI_API_TOKEN；为避免泄露，启动日志不显示该值。"
  token_hint="你设置的 SHUYI_API_TOKEN"
fi

echo "后端已映射到工作区端口 ${SHUYI_HOST_PORT}；公网地址请在 VS Code PORTS 面板查看。"
echo "GitHub Pages 的 VITE_API_BASE_URL 应填写：<PORTS 面板公网地址>/api/v1"
echo "请求头格式：Authorization: Bearer <$token_hint>"
echo "容器内 FastAPI 端口为 8000；CNB 工作区对外预览端口为 ${SHUYI_HOST_PORT}。"

if [ "${SHUYI_CNB_LAUNCH_DRY_RUN:-0}" = "1" ]; then
  echo "SHUYI_CNB_LAUNCH_DRY_RUN=1，跳过 docker compose 启动。"
  exit 0
fi

export SHUYI_MODEL_AUTO_DOWNLOAD="${SHUYI_MODEL_AUTO_DOWNLOAD:-1}"
docker compose -f compose.cuda.yaml down --remove-orphans || true
docker compose -f compose.cuda.yaml up --build
