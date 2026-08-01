# 书弈 Agent

书弈 Agent（Shuyi Agent）是基于 Agent 的多人有声书自动配音工作台，面向中文小说配音制作。v0.4.0 将流程拆成三个可追踪版本的运行时 Agent：小说解析、角色分析和配音编排。模型结果可以人工修改，运行时不会生成或执行模型返回的 Python 代码。

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
- v1 接口使用 `Authorization: Bearer <SHUYI_API_TOKEN>`；密钥只能通过本地 `.env` 或部署环境注入。

## Docker CPU / GPU

CPU 启动：

```bash
docker compose -f compose.cpu.yaml up --build
```

CUDA 启动需要 NVIDIA 驱动、Docker Engine 和 NVIDIA Container Toolkit：

```bash
docker compose -f compose.cuda.yaml up --build
```

两个配置都以非 root 用户运行，公开 `8000` 端口，并使用命名卷持久化 `/data` 与 `/models`。监督器同时启动 FastAPI 和只监听 `127.0.0.1:7811` 的 TTS；任一进程退出都会终止另一进程，容器健康检查要求两者都就绪。健康检查留出 5 分钟模型初始化时间。

首次启动按固定 commit revision 优先从 ModelScope 下载 Base 与 VoiceDesign 模型，失败后回退 Hugging Face。每个模型使用独立文件锁，下载到同一文件系统的临时目录，完成 SHA-256 校验和标记后再原子切换；后续启动重新校验缓存。设置 `SHUYI_MODEL_AUTO_DOWNLOAD=0` 可禁用下载并自行挂载模型。

模型体积较大，下载失败不会删除用户已存在的非空模型目录。需要重新下载时，应先停止容器并自行备份、检查对应命名卷，不要直接清理整个 Docker 数据目录。

## 环境变量

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `SHUYI_API_TOKEN` | v1 API Bearer token | 空，调用受保护接口会被拒绝 |
| `SHUYI_CORS_ORIGINS` | 允许的浏览器来源，逗号分隔 | 空 |
| `SHUYI_DEVICE` | `auto`、`cpu` 或 `cuda` | `auto` |
| `SHUYI_DATA_DIR` | 持久数据目录 | 容器内 `/data` |
| `SHUYI_MODEL_DIR` | 模型缓存根目录 | 容器内 `/models` |
| `SHUYI_MODEL_AUTO_DOWNLOAD` | 首次启动自动下载 | `1` |
| `SHUYI_TTS_MODEL_ID` | 两个模型源共用的 Base 模型 ID | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` |
| `SHUYI_TTS_VOICE_DESIGN_MODEL_ID` | 两个模型源共用的 VoiceDesign 模型 ID | `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` |
| `SHUYI_MODELSCOPE_TTS_REVISION` | Base 模型固定 ModelScope commit | `dfb4a462...` |
| `SHUYI_HUGGINGFACE_TTS_REVISION` | Base 模型固定 Hugging Face commit | `fd4b2543...` |
| `SHUYI_MODELSCOPE_VOICE_DESIGN_REVISION` | VoiceDesign 模型固定 ModelScope commit | `8dd530db...` |
| `SHUYI_HUGGINGFACE_VOICE_DESIGN_REVISION` | VoiceDesign 模型固定 Hugging Face commit | `5ecdb673...` |
| `MODELSCOPE_API_TOKEN` | ModelScope 受限模型访问 token | 空 |
| `HF_TOKEN` | Hugging Face 私有或受限模型访问 token | 空 |
| `SILICONFLOW_API_KEY` | 语句划分服务密钥 | 空 |
| `DEEPSEEK_API_KEY` | 章节/角色分析服务密钥 | 空 |
| `VITE_API_BASE_URL` | 前端构建时 API 地址 | 本地为 `/api/v1` |

全部环境变量示例见 `.env.example`。

## GitHub Pages

`.github/workflows/pages.yml` 在 `main` 分支前端文件变化时构建并部署静态站点。先在仓库 Settings > Pages 中选择 GitHub Actions，再按需配置仓库变量 `VITE_API_BASE_URL`。Pages 只托管前端，不提供 FastAPI 或模型服务；生产 API 必须启用 HTTPS、Bearer token 和准确的 CORS 来源。

## CNB 镜像发布模板

`.cnb.yml` 是可移植模板：先运行 CPU 契约测试，再在支持 NVIDIA Container Toolkit 的 GPU runner 上构建 CPU/CUDA 镜像并调用本地 TTS 完成真实音频推理。推理成功后始终推送 `${CNB_COMMIT_SHA}-cpu` 和 `${CNB_COMMIT_SHA}-cuda`；仅在 `CNB_TAG=v0.4.0` 时额外推送不可由普通分支流水线覆盖的 `v0.4.0-cpu` 与 `v0.4.0-cuda`。使用前在 CNB 仓库密钥中配置 registry 凭据和必要的模型 token，并根据实际执行器调整 Docker/GPU 服务声明。该模板不代表项目承诺长期托管任何公共镜像。

## 验证

```bash
uv run pytest -q
npm --prefix frontend test
npm --prefix frontend run build
docker compose -f compose.cpu.yaml config
docker compose -f compose.cuda.yaml config
```

真实 TTS 验收还需要已下载模型、足够内存或显存及一段授权明确的参考音频。
