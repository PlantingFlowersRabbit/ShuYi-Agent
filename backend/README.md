# 书翼 Agent 后端

后端基于 FastAPI，包含小说解析、角色/音色管理、配音工作流、SQLite 仓储和本地 Qwen3-TTS 服务。

## 本地启动

在仓库根目录执行：

```bash
cp .env.example .env
uv sync --group backend --group tts
uv run uvicorn backend.app.api.app:app --reload --host 127.0.0.1 --port 8000
```

健康检查为 `GET /health/ready`，OpenAPI 为 `/openapi.json`，交互文档为 `/docs`。`/api/v1/*` 接口要求 `Authorization: Bearer <NOVELVOICE_API_TOKEN>`。

## TTS 服务

API 可按模型配置启动 `backend/tts/qwen3_tts_server.py`。本地模型路径使用相对路径或环境变量，不依赖个人绝对路径：

```dotenv
QWEN3_TTS_MODEL_PATH=./models/Qwen3-TTS-12Hz-1.7B-Base
QWEN3_TTS_VOICE_DESIGN_MODEL_PATH=./models/Qwen3-TTS-12Hz-1.7B-VoiceDesign
QWEN3_TTS_DEVICE=cpu
QWEN3_TTS_BASE_URL=http://127.0.0.1:7811
```

容器首次启动由 `scripts/container/download_models.py` 下载模型到持久卷。脚本使用完成标记识别缓存，下载过程写入同一文件系统的临时目录，成功后再原子切换；已有非空目录不会被覆盖。

## 容器

`Dockerfile` 提供 `cpu-runtime` 与 `cuda-runtime` 两个目标，均以 `novelvoice` 非 root 用户运行。Compose 配置挂载：

- `/models`：Hugging Face 模型与完成标记；
- `/data`：持久业务数据目录，`/app/outputs` 链接到其中的 `outputs/`。

CUDA 运行需要 NVIDIA Container Toolkit。CPU/CUDA 配置分别设置 `NOVELVOICE_DEVICE` 与 `QWEN3_TTS_DEVICE`。

## 验证

```bash
uv run pytest -q tests/test_v0_4_api_contract.py
uv run pytest -q tests/test_v0_4_persistence_contract.py
uv run pytest -q tests/test_model_downloader.py
```

API 测试使用本地替身验证边界；真实模型和 TTS 仍需在目标硬件上单独验收。
