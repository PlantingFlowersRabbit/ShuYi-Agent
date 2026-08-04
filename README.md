<!-- markdownlint-disable first-line-h1 -->
<!-- markdownlint-disable html -->
<!-- markdownlint-disable no-duplicate-header -->

<div align="center">
  <img src="figures/shuyi-agent-zh.svg" width="60%" alt="书弈 Agent" />
</div>
<hr>
<div align="center" style="line-height: 1;">
  <a href="https://plantingflowersrabbit.github.io/ShuYi-Agent/"><img alt="Homepage"
src="https://img.shields.io/badge/Homepage-ShuYi%20Agent-536af5?color=536af5&logo=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgoAAAANSUhEUgAAACAAAAAUCAMAAADbT899AAAACVBMVEUAAAAFBjgf5cjIvfT7AAAAAXRSTlMAQObYZgAAAIxJREFUKM91UYsSwCAIEv%2F%2Fo%2BczZVveNQmJWYpUAJA%2FvLimF9xl9TB%2BIDlCLSdtX8fbxclEcbbhW5C1clIWSAu6HALBMRBoekK7j3RAHI%2FWvS3beD2SreJHoJB0uAlAv7gIoJVGsJrcMU2ea54bNhZ6qHnKA%2Fgl6az25GjUNae6B48cWzIb%2Bca1QApmHpVoAfvrulY2AAAAAElFTkSuQmCC&logoColor=white"/></a>
<a href="https://github.com/PlantingFlowersRabbit/ShuYi-Agent"><img alt="GitHub"
src="https://img.shields.io/badge/GitHub-%20ShuYi%20Agent-181717?logo=github&logoColor=white"/></a>
<a href="https://cnb.cool/gj-code/ShuYi-Agent"><img alt="CNB"
src="https://img.shields.io/badge/CNB-ShuYi%20Agent-1f6feb?color=fc630a&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjMyMCIgdmlld0JveD0iMCAwIDMyMCAzMjAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI%2BCjxwYXRoIGQ9Ik0yMjguOTA2IDQwLjI0MTJDMjI5Ljg4MiAzNy41MTA4IDIyOC45MDYgMzQuMzkwMyAyMjYuNzU5IDMyLjQ0QzIxOS4zNDIgMjYuMDA0IDIwMC43OTkgMTIuMzUxOSAxNzMuMDgyIDEwLjQwMTZDMTQxLjg1MiA4LjA2MTIxIDEyMi41MjggMTYuNDQ3NSAxMTIuNzY5IDIyLjY4ODVDMTA4LjQ3NCAyNS40MTg5IDEwOC4yNzkgMzEuNDY0OSAxMTIuMTgzIDM0LjM5MDNMMTkxLjYyNSA5Ni4yMTQ5QzE5OC42NTIgMTAxLjY3NiAyMDguOTk3IDk4LjU1NTMgMjExLjcyOSA5MC4xNjlMMjI4LjcxMSA0MC4yNDEySDIyOC45MDZaIiBmaWxsPSIjRkY2MjAwIi8%2BCjxwYXRoIGQ9Ik0zMi45MzgxIDIyMy41NjRDMjkuNjE5OSAyMjUuNzEgMjguMjUzNiAyMjkuODA1IDI5LjIyOTUgMjMzLjUxMUMzMi4xNTczIDI0NC40MzIgNDEuMzMxMiAyNjYuODYxIDY2LjkwMDkgMjg3LjUzNEM5Mi40NzA2IDMwOC4wMTIgMTIyLjcyNSAzMTAuMzUzIDEzNS42MDcgMzA5Ljk2M0MxMzkuNTExIDMwOS45NjMgMTQyLjgyOSAzMDcuNDI3IDE0NCAzMDMuNzIyTDE5NC45NDUgMTQyLjYyN0MxOTguNjUzIDEzMC45MjUgMTg1LjU3NiAxMjEuMTczIDE3NS40MjYgMTI3Ljk5OUwzMi45MzgxIDIyMy41NjRaIiBmaWxsPSIjRkY2MjAwIi8%2BCjxwYXRoIGQ9Ik03MC4yMTY5IDUzLjQ5NTVDNjcuNjc5NCA1Mi41MjAzIDY0Ljk0NjggNTIuNzE1MyA2Mi42MDQ1IDUzLjg4NTVDNTMuMjM1NSA1OC45NTYzIDI5LjAzMiA3NC43NTM4IDE2LjU0IDEwNy4zMjRDNi43ODA1NCAxMzIuMjg4IDEwLjA5ODcgMTU5Ljk4MiAxMi44MzE0IDE3My40MzlDMTMuNjEyMSAxNzcuOTI1IDE4LjI5NjcgMTgwLjQ2IDIyLjU5MDggMTc4LjcwNUwxNzUuNDI0IDExOS4wMjZDMTg2LjM1NCAxMTQuNzM1IDE4Ni4zNTQgOTkuMzI3NiAxNzUuNDI0IDk1LjAzNjlMNzAuMjE2OSA1My40OTU1WiIgZmlsbD0iI0ZGNjIwMCIvPgo8cGF0aCBkPSJNMjk3LjAzIDE2OC45NjhDMzAxLjUxOSAxNzEuODkzIDMwNy41NyAxNjkuMzU4IDMwOC4zNTEgMTY0LjA5MkMzMTAuMzAzIDE1MC4wNSAzMTIuMDYgMTI1Ljg2NiAzMDQuMDU3IDEwNy4zMzhDMjkzLjMyMSA4Mi45NTkxIDI3NC45NzQgNjcuNzQ2OCAyNjYuMTkgNjEuNzAwOEMyNjMuNDU4IDU5Ljc1MDUgMjU5Ljc0OSA1OS45NDU2IDI1Ny4yMTIgNjIuMjg1OUwyMTguNTY0IDk2LjQxNjJDMjEyLjMxOCAxMDIuMDcyIDIxMi45MDQgMTEyLjAxOSAyMTkuOTMxIDExNi42OTlMMjk3LjAzIDE2OC45NjhaIiBmaWxsPSIjRkY2MjAwIi8%2BCjxwYXRoIGQ9Ik0xODkuMDg5IDI5OS40MjhDMTg4LjY5OSAzMDMuOTE0IDE5Mi42MDMgMzA3LjgxNCAxOTcuMDkyIDMwNy4yMjlDMjExLjczMSAzMDUuNjY5IDI0MS43OSAyOTkuODE4IDI2NC4yMzcgMjc4LjM2NUMyODYuMDk4IDI1Ny40OTYgMjkzLjMyIDIzMi43MjggMjk1LjI3MiAyMjIuNzgxQzI5NS44NTggMjIwLjA1MSAyOTUuMjcyIDIxNy4zMiAyOTMuNTE1IDIxNS4xNzVMMjI1Ljk4IDEzMS44OTdDMjE4Ljc1OCAxMjIuOTI1IDIwNC4xMTkgMTI3LjQxMSAyMDMuMTQzIDEzOC45MThMMTg5LjA4OSAyOTkuMjMzVjI5OS40MjhaIiBmaWxsPSIjRkY2MjAwIi8%2BCjwvc3ZnPg%3D%3D"/></a>
<a href="https://github.com/PlantingFlowersRabbit/ShuYi-Agent/blob/main/LICENSE"><img alt="Code License"
src="https://img.shields.io/badge/Code_License-MIT-f5de53?&color=f5de53"/></a>
</div>

## 目录

1. [简介](#简介)
2. [快速开始](#快速开始)
3. [项目结构](#项目结构)
4. [本地开发](#本地开发)
5. [API 与 OpenAPI](#api-与-openapi)
6. [制作任务 Planner](#制作任务-planner)
7. [短期与长期记忆机制](#短期与长期记忆机制)
8. [Tool Calling Registry](#tool-calling-registry)
9. [Story Bible RAG 与 Qdrant](#story-bible-rag-与-qdrant)
10. [项目工作区与审稿队列](#项目工作区与审稿队列)
11. [Agent 追踪与上下文报告](#agent-追踪与上下文报告)
12. [Docker CPU / GPU](#docker-cpu--gpu)
13. [环境变量](#环境变量)
14. [GitHub Pages](#github-pages)
15. [CNB 镜像发布模板](#cnb-镜像发布模板)
16. [验证](#验证)

## 简介

书弈 Agent（Shuyi Agent）是基于 Agent 的多人有声书自动配音工作台，面向中文小说配音制作。v0.6.5 新增制作任务 Planner，可把“把当前章节处理到可导出”拆成可执行、可复盘、可恢复的工具计划；v0.6.4 新增短期 Run Memory、长期 Story Memory 可信度策略和错误记忆防污染；v0.6.3 新增 Tool Calling Registry、声明式工具 schema、JSON-plan fallback、项目级权限隔离和 Trace Viewer 工具调用审计；v0.6.2 新增 Story Bible RAG、OpenAI-compatible embedding、可选 Qdrant 向量库、SQLite 文本检索降级和带来源引用的角色证据；v0.6.1 增加项目/书籍工作区、按 `project_id` 隔离的输出路径、生成前/导出前质量检查和审稿队列；v0.6.0 已加入 Agent Run History、Prompt SHA、token/context 预算报告和可审计追踪详情。项目同时保留 v0.5.5 的公开 v1 API、前端一键后台下载并部署 TTS 模型、OpenAI SDK 兼容文本模型配置，以及“运行时不会生成或执行模型返回 Python 代码”的安全边界。

## 快速开始

本地 uv 脚本默认面向中国网络环境，使用阿里 PyPI 源与 npmmirror。需要 Python 3.11+、Node.js 22+；Linux 环境下脚本会尝试安装 `ffmpeg`、`libsndfile1` 与 `sox`。

CPU 启动：

```bash
bash scripts/local/start-uv-cpu.sh
```

GPU 启动：

```bash
bash scripts/local/start-uv-gpu.sh
```

GPU 脚本默认使用 `TORCH_BACKEND=cu128`，会创建独立的 `.venv-gpu`，不覆盖 CPU 脚本使用的 `.venv`。如需切换 PyTorch CUDA 后端，可在启动前覆盖环境变量：

```bash
TORCH_BACKEND=cu126 bash scripts/local/start-uv-gpu.sh
```

两个脚本都会以前台方式启动后端 `0.0.0.0:8000` 与前端 `0.0.0.0:5173`，不写日志文件，按 `Ctrl-C` 会同时停止前后端。TTS 模型默认不随主应用启动下载，首次使用可在前端“模型配置”中点击下载并部署；模型尚未部署前 `/health/ready` 中 `tts` 会显示 `not_ready`。

如果只想临时启动后端并改端口，可以直接运行 uvicorn，例如把后端监听到 `6006`：

```bash
.venv/bin/python -m uvicorn backend.app.api.app:app --host 0.0.0.0 --port 6006
```

GPU 环境只启动后端时可使用：

```bash
SHUYI_DEVICE=cuda QWEN3_TTS_DEVICE=cuda \
  .venv-gpu/bin/python -m uvicorn backend.app.api.app:app --host 0.0.0.0 --port 6006
```

## 项目结构

- `frontend/`：React、TypeScript 与 Vite 工作台，可本地运行或发布到 GitHub Pages。
- `backend/`：FastAPI API、领域逻辑、SQLite 仓储与 Qwen3-TTS 本地服务。
- `backend/app/agents/`：统一的运行时 Agent 注册表与执行契约。
- `backend/app/prompts/`：随产品发布、可审计的版本化 Agent 提示词模板。
- `assets/`：可再分发测试素材及许可证记录。
- `models/`：本地模型缓存，除说明文件外不纳入 Git。
- `outputs/`：音频与导出结果，除说明文件外不纳入 Git。

## 本地开发

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/) 和 Node.js 22+。

```bash
cp .env.example .env
uv sync --group backend --group tts
uv run uvicorn backend.app.api.app:app --reload --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

前端默认在 `http://127.0.0.1:5173`，API 在 `http://127.0.0.1:8000`。完整开发说明见 [frontend/README.md](frontend/README.md) 与 [backend/README.md](backend/README.md)。

## API 与 OpenAPI

- 健康检查：`GET /health/live`、`/health/startup`、`/health/ready`
- 项目工作区：`GET /api/v1/projects`、`POST /api/v1/projects`、`GET /api/v1/projects/{project_id}`、`DELETE /api/v1/projects/{project_id}`
- 质量检查：`POST /api/v1/projects/{project_id}/quality-check`
- 审稿队列：`POST /api/v1/projects/{project_id}/review-queue`
- Story Memory 索引：`POST /api/v1/projects/{project_id}/memory/index`
- Story Memory 检索：`POST /api/v1/projects/{project_id}/memory/search`
- Story Bible 事实：`GET /api/v1/projects/{project_id}/story-bible`
- Story Bible 写入：`POST /api/v1/projects/{project_id}/story-bible/facts`
- Story Bible 纠错：`PATCH /api/v1/projects/{project_id}/story-bible/facts/{fact_id}`
- Story Memory 上下文：`GET /api/v1/projects/{project_id}/story-bible/memory-context?query=...`
- Run Memory 恢复：`GET /api/v1/projects/{project_id}/run-memory/{run_id}`
- 制作任务 Planner：`POST /api/v1/projects/{project_id}/planner/plan`、`POST /planner/execute`、`POST /planner/review`、`GET /planner/runs/{run_id}`
- Tool Registry：`GET /api/v1/tools`
- Tool Calling 执行：`POST /api/v1/projects/{project_id}/tools/execute`
- Agent 追踪列表：`GET /api/v1/agent-runs`
- Agent 追踪详情：`GET /api/v1/agent-runs/{run_id}?agent_id=role_analyzer`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`
- Swagger UI：`http://127.0.0.1:8000/docs`
- v1 接口默认公开访问，不再需要后端访问令牌；文本模型 API Key 可在前端临时输入，后端只在运行内存中读取，不写入持久化快照。

## 制作任务 Planner

v0.6.5 新增制作任务 Planner，把“把当前章节处理到可导出”这类目标拆成计划树，并通过 Tool Registry 执行项目状态检查、Story Bible 检索、台词查询、长句拆分建议、TTS 健康检查和导出前质量检查。Planner 不执行未注册工具，不让模型直接运行任意代码；每个工具步骤仍沿用 v0.6.3 的项目权限、参数校验和失败摘要。

Planner run 会写入 SQLite `planner_runs`，同时同步到 `agent_runs` checkpoint、短期 Run Memory 和 `planner_step_*` events。`POST /planner/execute` 支持从已保存 `run_id` 继续执行，也支持 `max_steps` 做分批执行；工具失败后状态转为 `waiting_for_user`，并返回 `recovery_suggestions`。`POST /planner/review` 会输出 remaining issues、是否需要人工介入，以及“修正输入后从失败步骤继续”的恢复建议。

前端主页面侧栏新增 **制作任务 Planner** 面板，默认目标为“把当前章节处理到可导出”，支持生成计划、执行计划和复盘计划，并展示每一步的状态、工具名、失败原因与恢复建议。这个阶段的面试讲解重点是：目标拆解、受控工具执行、暂停/继续、失败恢复、Reviewer 复盘和 Human-in-the-loop。

## 短期与长期记忆机制

v0.6.4 将记忆分为两层：短期 Run Memory 记录一次执行中的目标、计划、步骤、工具调用、中间结果、错误、reflection 和最终输出；长期 Story Memory 保存角色事实、别名、关系、声线设定、用户确认纠错、术语读音和被拒绝事实。

长期记忆使用 `model_suggested`、`user_confirmed`、`system_verified`、`rejected` 四档可信度。模型写入即使声明 `user_confirmed` 也会降级为 `model_suggested`；用户纠错默认提升为 `user_confirmed`；`rejected` 会保留在库中用于防重复犯错，但不会进入 prompt facts 或读音查询工具的可信事实列表。

`GET /story-bible/memory-context` 会把事实分成 `facts_for_prompt`、`candidate_facts` 和 `rejected_facts`：Prompt 只优先使用 `user_confirmed` / `system_verified`，`model_suggested` 仅作为候选证据，`rejected` 只用于审计和防污染。`POST /tools/execute` 会自动保存 Run Memory，之后可通过 `/run-memory/{run_id}` 恢复一次 Agent 执行的短期状态。

## Tool Calling Registry

v0.6.3 新增声明式 Tool Registry。`GET /api/v1/tools` 会返回每个工具的 `tool_name`、`description`、`input_schema`、`output_schema`、`permission_scope` 和 `timeout_seconds`，不暴露 Python implementation。当前工具覆盖 Story Memory 检索、项目质量状态、角色列表/详情、台词查询、长文本拆分建议、文本守恒校验、TTS 健康检查、音色试听请求和术语读音查询。

如果模型不支持原生 tool calling，可使用 JSON-plan fallback：

```json
{
  "run_id": "tool-run-001",
  "agent_id": "role_analyzer",
  "tool_calls": [
    {"tool_name": "search_story_memory", "arguments": {"query": "小舟", "top_k": 3}}
  ]
}
```

执行入口为 `POST /api/v1/projects/{project_id}/tools/execute`。后端只执行注册工具，拒绝未注册工具；请求体里的 `project_id` 如与路径不一致会返回 403，防止模型跨项目读取；工具失败会以 `status=failed`、`failure`、`duration_ms` 写入结果，而不是执行任意代码或吞掉错误。每次工具计划都会保存到 Agent trace 的 `tool_calls` 字段，前端 Agent追踪页展示工具名、参数摘要、返回摘要、耗时和失败原因。

## Story Bible RAG 与 Qdrant

v0.6.2 将小说正文、设定集、术语表、角色档案和台词沉淀为项目级 Story Memory。`/memory/index` 会为每个 chunk 保存 `project_id`、`source_id`、`source_type`、章节/段落/台词锚点、字符范围、原文和 metadata，并从 Story Bible、术语表与角色别名派生可人工纠错的 facts。

检索结果统一返回 `source_citations`，包含 `source_id`、`source_type`、`chapter_id`、`paragraph_id`、`utterance_id`、`char_start`、`char_end` 和 `snippet`。角色分析 Agent 会把可检索到的证据附到候选角色上；没有来源支撑的候选会保持或升级为 `needs_human_review=true`，避免把模型猜测写成事实。

默认不要求外部服务：未配置 `SHUYI_EMBEDDING_API_KEY` 时，索引接口会返回 `embedding_status=skipped_missing_api_key`，数据仍写入 SQLite，`/memory/search` 使用 `retrieval_mode=sqlite_lexical` 做本地文本检索。配置 embedding key 与 `SHUYI_QDRANT_URL` 后，索引会写入 Qdrant，检索接口会优先返回 `retrieval_mode=qdrant_vector`；embedding 或 Qdrant 临时失败时会带 message 回落到 SQLite。

本地启动可选 Qdrant：

```bash
docker compose -f compose.qdrant.yaml up -d
export SHUYI_QDRANT_URL=http://127.0.0.1:${SHUYI_QDRANT_PORT:-6333}
```

Story Bible fact 更新只允许修改 `confidence`、`notes` 和 `metadata`，便于把用户确认过的纠错沉淀为长期记忆，同时保留 `rejected` 事实防止错误记忆反复污染后续 Agent 输出。

## 项目工作区与审稿队列

v0.6.1 将一次性上传流程升级为可恢复的项目工作区雏形。后端使用 SQLite `projects` 表保存项目元数据，并为每个项目返回隔离输出目录：`outputs/{project_id}/audio/` 与 `outputs/{project_id}/exports/`。`default` 项目会自动存在，用于兼容旧数据和未显式选择项目的工作流。

前端主页面侧栏新增 **项目工作区**、**质量检查面板** 和 **审稿队列**：

- 项目工作区支持新建、打开最近项目、删除非默认项目；最近项目顺序保存在浏览器 `localStorage`。
- 质量检查汇总当前章节/整本书生产阻塞项：未划分、未选角色、未配音、配音失败、超长台词、重复音色、角色无音色和 `needs_human_review`。
- 生成前检查重点判断是否可以继续批量配音；导出前检查要求配音、角色、音色和人工复核项全部清理。
- 审稿队列集中展示需要 Human-in-the-loop 的台词与失败项，并提供跳转、批量确认、批量改角色和批量重试入口。

这个阶段的面试讲解重点是：为什么需要 `project_id` 隔离、GitHub Pages 多人访问时如何避免数据串线、以及如何把模型低置信度/失败状态产品化为可审核工作流。

## Agent 追踪与上下文报告

v0.6.0 在 SQLite 中单独保存 `agent_run_traces`，不替代原有轻量 `agent_runs` checkpoint 和 SSE `events`。完成角色分析或配音编排后，前端 “Agent追踪 / Run History” 页面会展示最近运行记录和详情。

每条 trace 包含：

- 运行元数据：`run_id`、`project_id`、`chapter_id`、Agent 名称、模型名、provider base URL。
- Prompt 追踪：`prompt_id`、`prompt_version`、`prompt_sha256`，不保存或展示 API key。
- Token/context 报告：系统 prompt、输入、输出的近似 token 数，context window、预留输出 token 和预算策略。
- Tool Calls：工具名、权限范围、参数摘要、返回摘要、耗时和失败原因。
- 输出审计：输入摘要、原始模型输出、解析结果、JSON 校验状态、validation errors、reflection 记录、最终决策和人工复核数量。

当前 token 估算使用可替换的启发式策略：中文约 1.7 字/token，非中文约 4 字/token；`SHUYI_CONTEXT_WINDOW` 或 `SHUYI_TEXT_MODEL_CONTEXT_WINDOW` 可覆盖默认上下文窗口。

## Docker CPU / GPU

CPU 启动：

```bash
docker compose -f compose.cpu.yaml up --build
```

CUDA 启动需要 NVIDIA 驱动、Docker Engine 和 NVIDIA Container Toolkit：

```bash
docker compose -f compose.cuda.yaml up --build
```

两个配置都以非 root 用户运行，默认将容器内 FastAPI `0.0.0.0:8000` 显式发布到宿主机 `0.0.0.0:8000`；可用 `SHUYI_HOST_PORT=8686` 改为其他宿主机端口。命名卷会持久化 `/data` 与 `/models`。容器默认先启动 FastAPI；TTS 模型由前端“模型配置 > 下载并部署”按钮在后台下载、校验并启动，过程中其他不依赖 TTS 的 API 可继续使用。

模型下载按固定 commit revision 优先从 ModelScope 下载 Base 与 VoiceDesign 模型，失败后回退 Hugging Face。每个模型使用独立文件锁，下载到同一文件系统的临时目录，完成 SHA-256 校验和标记后再原子切换；后续点击部署会复用已校验缓存。设置 `SHUYI_MODEL_AUTO_DOWNLOAD=1` 且 `SHUYI_START_TTS_ON_BOOT=1` 可恢复容器启动时下载并启动 TTS 的验收/CI 行为。

模型体积较大，下载失败不会删除用户已存在的非空模型目录。需要重新下载时，应先停止容器并自行备份、检查对应命名卷，不要直接清理整个 Docker 数据目录。

## 环境变量

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `SHUYI_HOST_PORT` | Docker 暴露到宿主机的后端端口；CNB 启动脚本默认用 `8000` | `8000` |
| `SHUYI_DEVICE` | `auto`、`cpu` 或 `cuda` | `auto` |
| `SHUYI_DATA_DIR` | 持久数据目录 | 容器内 `/data` |
| `SHUYI_MODEL_DIR` | 模型缓存根目录 | 容器内 `/models` |
| `SHUYI_MODEL_AUTO_DOWNLOAD` | 启动时自动下载模型；普通运行建议由前端按钮触发 | `0` |
| `SHUYI_TTS_MODEL_ID` | 两个模型源共用的 Base 模型 ID | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` |
| `SHUYI_TTS_VOICE_DESIGN_MODEL_ID` | 两个模型源共用的 VoiceDesign 模型 ID | `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` |
| `SHUYI_MODELSCOPE_TTS_REVISION` | Base 模型固定 ModelScope commit | `dfb4a462...` |
| `SHUYI_HUGGINGFACE_TTS_REVISION` | Base 模型固定 Hugging Face commit | `fd4b2543...` |
| `SHUYI_MODELSCOPE_VOICE_DESIGN_REVISION` | VoiceDesign 模型固定 ModelScope commit | `8dd530db...` |
| `SHUYI_HUGGINGFACE_VOICE_DESIGN_REVISION` | VoiceDesign 模型固定 Hugging Face commit | `5ecdb673...` |
| `MODELSCOPE_API_TOKEN` | ModelScope 受限模型访问 token | 空 |
| `HF_TOKEN` | Hugging Face 私有或受限模型访问 token | 空 |
| `SHUYI_TEXT_MODEL_API_KEY` | OpenAI SDK 兼容文本模型密钥，也可在前端临时输入 | 空 |
| `SHUYI_TEXT_MODEL_BASE_URL` | OpenAI SDK 兼容文本模型 Base URL | 空 |
| `SHUYI_TEXT_MODEL_NAME` | OpenAI SDK 兼容文本模型名称 | 空 |
| `SHUYI_CONTEXT_WINDOW` / `SHUYI_TEXT_MODEL_CONTEXT_WINDOW` | Agent trace 的上下文窗口估算值 | `32768` |
| `SHUYI_EMBEDDING_BASE_URL` | OpenAI-compatible embedding Base URL | `https://api.openai.com/v1` |
| `SHUYI_EMBEDDING_MODEL` | Story Memory 向量化模型 | `text-embedding-3-small` |
| `SHUYI_EMBEDDING_API_KEY_ENV` | 读取 embedding key 的环境变量名 | `SHUYI_EMBEDDING_API_KEY` |
| `SHUYI_EMBEDDING_API_KEY` | 默认 embedding API key；不要写入前端变量 | 空 |
| `SHUYI_EMBEDDING_TIMEOUT_SECONDS` | embedding 请求超时 | `60` |
| `SHUYI_QDRANT_URL` | 可选 Qdrant 服务地址；为空时使用 SQLite 文本检索 | 空 |
| `SHUYI_QDRANT_COLLECTION` | Qdrant collection 名称，使用全局 collection + `project_id` filter | `shuyi_story_memory` |
| `SHUYI_QDRANT_PORT` | `compose.qdrant.yaml` 暴露到本机的 Qdrant 端口 | `6333` |
| `VITE_API_BASE_URL` | 前端构建时 API 地址；可填完整 URL 或裸域名，裸域名会按 `https://域名/api/v1` 解析；也可在页面“模型配置 > 后端 API”运行时覆盖 | 本地为 `/api/v1` |

全部环境变量示例见 `.env.example`。

## CNB 启动与公网访问

CNB 仓库页点击 **启动 ShuYi-Agent** 后会执行 `scripts/cnb/start-shuyi-agent.sh`。脚本会先停止旧的同名 Compose 服务，再把容器内 FastAPI `0.0.0.0:8000` 显式映射到 CNB 工作区的 `0.0.0.0:8000`，满足 WebIDE/VS Code PORTS 面板要求服务监听 `0.0.0.0` 的访问条件。仓库同时提供 `.devcontainer/devcontainer.json` 的 `forwardPorts: [8000]` 和 `.vscode/settings.json` 的端口侦测设置，用于让 VS Code/CNB 自动转发 8000。CNB 的公网 Forwarded Address 每次可能变化，脚本不再猜测或打印具体公网域名；请以 VS Code PORTS 面板显示的 Forwarded Address 为准。

GitHub Pages 访问 CNB 后端时，可把 PORTS 面板显示的公网地址填到页面“模型配置 > 后端 API”，例如 `https://faho62u6pf-8000.cnb.run/api/v1`；也可只填裸域名，前端会自动解析为 `https://<域名>/api/v1`。后端业务 API 不再使用访问令牌和浏览器来源白名单，会统一允许无凭据跨域预检，因此 CNB Forwarded Address 每次变化时只需要更新前端填写的后端 API 地址。如果希望构建产物默认指向固定后端，也可以把同一地址配置为仓库变量 `VITE_API_BASE_URL`。模型配置页的 TTS 默认值按 CNB/Docker 后端显示为 `http://127.0.0.1:7811`、`/models/Qwen3-TTS-12Hz-1.7B-Base`、`/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign`；这是后端容器内部连接 TTS 服务和读取模型权重的配置，不是前端连接 FastAPI 后端的地址。

## GitHub Pages

`.github/workflows/pages.yml` 在 `main` 分支每次更新时构建静态站点并发布到 `gh-pages` 分支。先在仓库 Settings > Pages 中选择从 `gh-pages` 分支发布，再按需配置仓库变量 `VITE_API_BASE_URL`；临时 CNB 后端也可以直接在页面“模型配置 > 后端 API”中保存。Pages 只托管前端，不提供 FastAPI 或模型服务；生产 API 应启用 HTTPS，当前公开 API 模式下无需额外维护 Pages 或 CNB 的 CORS 白名单。

## CNB 镜像发布模板

`.cnb.yml` 是可移植模板：先运行 CPU 契约测试，再在支持 NVIDIA Container Toolkit 的 GPU runner 上构建 CPU/CUDA 镜像并调用本地 TTS 完成真实音频推理。推理成功后始终推送 `${CNB_COMMIT_SHA}-cpu` 和 `${CNB_COMMIT_SHA}-cuda`；仅在 `CNB_TAG=v0.6.4` 时额外推送不可由普通分支流水线覆盖的 `v0.6.4-cpu` 与 `v0.6.4-cuda`。使用前在 CNB 仓库密钥中配置 registry 凭据和必要的模型 token，并根据实际执行器调整 Docker/GPU 服务声明。该模板不代表项目承诺长期托管任何公共镜像。

## 验证

```bash
uv run pytest -q
npm --prefix frontend test
npm --prefix frontend run build
docker compose -f compose.cpu.yaml config
docker compose -f compose.cuda.yaml config
docker compose -f compose.qdrant.yaml config
```

真实 TTS 验收还需要已下载模型、足够内存或显存及一段授权明确的参考音频。
