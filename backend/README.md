# 书弈 Agent 后端

后端基于 FastAPI，包含小说解析、角色/音色管理、配音工作流、短期/长期记忆、Tool Calling Registry、Story Bible RAG、SQLite 仓储、可选 Qdrant 向量库和本地 Qwen3-TTS 服务。

## 本地启动

在仓库根目录执行：

```bash
cp .env.example .env
uv sync --group backend --group tts
uv run uvicorn backend.app.api.app:app --reload --host 127.0.0.1 --port 8000
```

健康检查为 `GET /health/ready`，OpenAPI 为 `/openapi.json`，交互文档为 `/docs`。`/api/v1/*` 接口默认公开访问，不再要求后端访问令牌。

## 项目工作区与质量检查

v0.6.1 新增项目工作区和 Human-in-the-loop 质量 API：

- `GET /api/v1/projects`：列出项目，默认包含兼容旧数据的 `default` 项目。
- `POST /api/v1/projects`：新建项目，并返回 `outputs/{project_id}/audio` 与 `outputs/{project_id}/exports` 隔离路径。
- `GET /api/v1/projects/{project_id}`：读取项目元数据和输出目录。
- `DELETE /api/v1/projects/{project_id}`：删除非默认项目；`default` 会返回 409。
- `POST /api/v1/projects/{project_id}/quality-check`：统计未划分、未选角色、未配音、配音失败、超长台词、重复音色、角色无音色和 `needs_human_review`。
- `POST /api/v1/projects/{project_id}/review-queue`：从质量报告中筛出可操作审稿项，支持按 issue、章节或角色过滤。

这些接口仍使用 SQLite 持久化，所有新 API 都会校验并规范化 `project_id`，避免路径穿越和项目输出串线。

## Story Bible RAG

v0.6.2 新增项目级 Story Memory 和 Story Bible API：

- `POST /api/v1/projects/{project_id}/memory/index`：把小说正文、设定集、术语表、角色档案和台词写入 `story_memory_chunks`，并派生 `story_bible_facts`。
- `POST /api/v1/projects/{project_id}/memory/search`：检索 Story Memory，返回统一的 `citation`，包含来源类型、章节/段落/台词锚点、字符范围和片段。
- `GET /api/v1/projects/{project_id}/story-bible`：读取当前项目的角色别名、术语读音、用户确认事实等长期记忆。
- `PATCH /api/v1/projects/{project_id}/story-bible/facts/{fact_id}`：只允许修改 `confidence`、`notes` 和 `metadata`，用于把用户纠错沉淀为 `user_confirmed` 或保留为 `rejected`。

没有配置 embedding key 时，索引仍写入 SQLite，检索返回 `retrieval_mode=sqlite_lexical`。配置 `SHUYI_EMBEDDING_API_KEY` 与 `SHUYI_QDRANT_URL` 后，索引会写入 Qdrant，检索优先返回 `retrieval_mode=qdrant_vector`；任一外部服务失败都会带 message 回落到 SQLite 文本检索。

本地启动 Qdrant：

```bash
docker compose -f compose.qdrant.yaml up -d
export SHUYI_QDRANT_URL=http://127.0.0.1:${SHUYI_QDRANT_PORT:-6333}
```

角色分析 Agent 会读取项目 Story Memory，并把检索到的来源引用写入 `role_candidates[].source_citations`。没有证据支撑的候选会标记 `needs_human_review=true`，避免把模型猜测直接变成长期事实。

## 短期与长期记忆

v0.6.4 新增 Run Memory 和长期 Story Memory 读写规则：

- `POST /api/v1/projects/{project_id}/story-bible/facts`：写入单条长期事实；用户纠错默认 `user_confirmed`，模型写入会被限制为 `model_suggested`，除非显式 `rejected`。
- `GET /api/v1/projects/{project_id}/story-bible/memory-context?query=林舟`：返回 `facts_for_prompt`、`candidate_facts` 和 `rejected_facts`，Prompt 只使用 `user_confirmed` / `system_verified`。
- `GET /api/v1/projects/{project_id}/run-memory/{run_id}`：恢复一次工具计划或 Agent run 的短期记忆，包括目标、计划、步骤、工具调用、错误、reflection 和最终输出。

`rejected` 事实不会被删除，会留在长期记忆中防止模型反复提出同一个错误事实；但它不会进入 `facts_for_prompt`，`lookup_pronunciation` 等工具也不会把它当作可信事实返回。

## Tool Calling Registry

v0.6.3 新增 Tool Registry 与 JSON-plan fallback：

- `GET /api/v1/tools`：列出注册工具的名称、描述、输入/输出 schema、权限范围和超时，不暴露 implementation。
- `POST /api/v1/projects/{project_id}/tools/execute`：执行单个 `tool_name` 或 `tool_calls` 数组，适配不支持原生 tool calling 的模型。

首批工具包括 `search_story_memory`、`get_project_status`、`list_roles`、`get_role_profile`、`query_utterances`、`suggest_long_text_split`、`check_text_conservation`、`check_tts_health`、`generate_voice_preview` 和 `lookup_pronunciation`。所有工具都以路径中的 `project_id` 为准；请求参数中出现不同 `project_id` 会返回 403，未注册工具返回 404。工具结果会写入 `agent_run_traces.tool_calls`，包含工具名、参数摘要、返回摘要、耗时和失败原因。

## Agent 追踪

v0.6.0 新增 `agent_run_traces` 持久化表和只读追踪 API：

- `GET /api/v1/agent-runs`：列出最近 Agent run trace。
- `GET /api/v1/agent-runs/{run_id}?agent_id=role_analyzer`：读取单次运行详情。

Trace 记录 prompt 版本与 SHA、模型配置摘要、token/context 估算、工具调用、输入摘要、原始模型输出、解析结果、校验状态、reflection 和最终决策。后端只保存 provider base URL 与模型名，不保存或回传 API key。

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
