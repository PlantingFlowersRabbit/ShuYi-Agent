# 书弈 Agent 后端

后端基于 FastAPI，包含小说解析、角色/音色管理、配音工作流、SQLite 仓储和本地 Qwen3-TTS 服务。

## 本地启动

在仓库根目录执行：

```bash
cp .env.example .env
uv sync --group backend --group tts
uv run uvicorn backend.app.api.app:app --reload --host 127.0.0.1 --port 8000
```

健康检查为 `GET /health/ready`，OpenAPI 为 `/openapi.json`，交互文档为 `/docs`。`/api/v1/*` 接口默认公开访问，不再要求后端访问令牌。

## TTS 服务

API 可按模型配置启动 `backend/tts/qwen3_tts_server.py`。本地模型路径使用相对路径或环境变量，不依赖个人绝对路径：

```dotenv
QWEN3_TTS_MODEL_PATH=./models/Qwen3-TTS-12Hz-1.7B-Base
QWEN3_TTS_VOICE_DESIGN_MODEL_PATH=./models/Qwen3-TTS-12Hz-1.7B-VoiceDesign
QWEN3_TTS_DEVICE=auto
QWEN3_TTS_BASE_URL=http://127.0.0.1:7811
```

容器默认先启动 FastAPI；TTS 固定监听 `127.0.0.1:7811`，由 `/api/v1/model-config/tts/deploy` 后台下载模型并启动，不会直接暴露到容器外。设置 `SHUYI_START_TTS_ON_BOOT=1` 可恢复启动时同时监督 TTS 的验收/CI 行为。

`scripts/container/download_models.py` 默认优先 ModelScope、失败后回退 Hugging Face；两个来源分别使用固定非空 revision。每个模型有文件锁，下载在唯一临时目录进行，生成文件内容 SHA-256 校验和与完成标记后原子切换。已有缓存会在部署时重新校验，冲突或损坏目录不会被覆盖。

## 容器

`Dockerfile` 提供 `cpu-runtime` 与 `cuda-runtime` 两个目标，均以 `shuyi` 非 root 用户运行。Compose 配置挂载：

- `/models`：ModelScope/Hugging Face 模型、锁文件与完成标记；
- `/data`：持久业务数据目录，`/app/outputs` 链接到其中的 `outputs/`。

CUDA 运行需要 NVIDIA Container Toolkit。`QWEN3_TTS_DEVICE=auto` 在 CUDA 可用时选择 `cuda:0` 和 `bfloat16`，否则选择 `cpu` 和 `float32`；显式 `cpu`、`cuda` 仍可用。CPU/CUDA Compose 会分别固定对应设备。

## 验证

```bash
uv run pytest -q tests/test_v0_4_api_contract.py
uv run pytest -q tests/test_v0_4_persistence_contract.py
uv run pytest -q tests/test_model_downloader.py
```

API 测试使用本地替身验证边界；真实模型和 TTS 仍需在目标硬件上单独验收。
