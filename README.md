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
2. [项目结构](#项目结构)
3. [本地开发](#本地开发)
4. [API 与 OpenAPI](#api-与-openapi)
5. [Docker CPU / GPU](#docker-cpu--gpu)
6. [环境变量](#环境变量)
7. [GitHub Pages](#github-pages)
8. [CNB 镜像发布模板](#cnb-镜像发布模板)
9. [验证](#验证)

## 简介

书弈 Agent（Shuyi Agent）是基于 Agent 的多人有声书自动配音工作台，面向中文小说配音制作。v0.5.2 取消后端访问令牌流程，支持前端一键后台下载并部署 TTS 模型，同时保留 OpenAI SDK 兼容文本模型配置；运行时不会生成或执行模型返回的 Python 代码。

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
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`
- Swagger UI：`http://127.0.0.1:8000/docs`
- v1 接口默认公开访问，不再需要后端访问令牌；文本模型 API Key 可在前端临时输入，后端只在运行内存中读取，不写入持久化快照。

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
| `VITE_API_BASE_URL` | 前端构建时 API 地址；可填完整 URL 或裸域名，裸域名会按 `https://域名/api/v1` 解析；也可在页面“模型配置 > 后端 API”运行时覆盖 | 本地为 `/api/v1` |

全部环境变量示例见 `.env.example`。

## CNB 启动与公网访问

CNB 仓库页点击 **启动 ShuYi-Agent** 后会执行 `scripts/cnb/start-shuyi-agent.sh`。脚本会先停止旧的同名 Compose 服务，再把容器内 FastAPI `0.0.0.0:8000` 显式映射到 CNB 工作区的 `0.0.0.0:8000`，满足 WebIDE/VS Code PORTS 面板要求服务监听 `0.0.0.0` 的访问条件。仓库同时提供 `.devcontainer/devcontainer.json` 的 `forwardPorts: [8000]` 和 `.vscode/settings.json` 的端口侦测设置，用于让 VS Code/CNB 自动转发 8000。CNB 的公网 Forwarded Address 每次可能变化，脚本不再猜测或打印具体公网域名；请以 VS Code PORTS 面板显示的 Forwarded Address 为准。

GitHub Pages 访问 CNB 后端时，可把 PORTS 面板显示的公网地址填到页面“模型配置 > 后端 API”，例如 `https://faho62u6pf-8000.cnb.run/api/v1`；也可只填裸域名，前端会自动解析为 `https://<域名>/api/v1`。后端业务 API 不再使用访问令牌和浏览器来源白名单，会统一允许无凭据跨域预检，因此 CNB Forwarded Address 每次变化时只需要更新前端填写的后端 API 地址。如果希望构建产物默认指向固定后端，也可以把同一地址配置为仓库变量 `VITE_API_BASE_URL`。模型配置页的 TTS 默认值按 CNB/Docker 后端显示为 `http://127.0.0.1:7811`、`/models/Qwen3-TTS-12Hz-1.7B-Base`、`/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign`；这是后端容器内部连接 TTS 服务和读取模型权重的配置，不是前端连接 FastAPI 后端的地址。

## GitHub Pages

`.github/workflows/pages.yml` 在 `main` 分支每次更新时构建静态站点并发布到 `gh-pages` 分支。先在仓库 Settings > Pages 中选择从 `gh-pages` 分支发布，再按需配置仓库变量 `VITE_API_BASE_URL`；临时 CNB 后端也可以直接在页面“模型配置 > 后端 API”中保存。Pages 只托管前端，不提供 FastAPI 或模型服务；生产 API 应启用 HTTPS，当前公开 API 模式下无需额外维护 Pages 或 CNB 的 CORS 白名单。

## CNB 镜像发布模板

`.cnb.yml` 是可移植模板：先运行 CPU 契约测试，再在支持 NVIDIA Container Toolkit 的 GPU runner 上构建 CPU/CUDA 镜像并调用本地 TTS 完成真实音频推理。推理成功后始终推送 `${CNB_COMMIT_SHA}-cpu` 和 `${CNB_COMMIT_SHA}-cuda`；仅在 `CNB_TAG=v0.5.2` 时额外推送不可由普通分支流水线覆盖的 `v0.5.2-cpu` 与 `v0.5.2-cuda`。使用前在 CNB 仓库密钥中配置 registry 凭据和必要的模型 token，并根据实际执行器调整 Docker/GPU 服务声明。该模板不代表项目承诺长期托管任何公共镜像。

## 验证

```bash
uv run pytest -q
npm --prefix frontend test
npm --prefix frontend run build
docker compose -f compose.cpu.yaml config
docker compose -f compose.cuda.yaml config
```

真实 TTS 验收还需要已下载模型、足够内存或显存及一段授权明确的参考音频。
