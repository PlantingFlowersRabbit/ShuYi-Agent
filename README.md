<!-- markdownlint-disable first-line-h1 -->
<!-- markdownlint-disable html -->
<!-- markdownlint-disable no-duplicate-header -->

<div align="center">
  <img src="figures/shuyi-agent-zh.svg" width="60%" alt="书弈 Agent" />
</div>
<hr>
<div align="center" style="line-height: 1;">
  <a href="https://plantingflowersrabbit.github.io/ShuYi-Agent/"><img alt="Homepage"
src="https://img.shields.io/badge/Homepage-ShuYi%20Agent-536af5?color=1fe5c8&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCAzOSIgc2hhcGUtcmVuZGVyaW5nPSJjcmlzcEVkZ2VzIj48cGF0aCBmaWxsPSIjMDUwNjM4IiBkPSJNMTcgMGg2djFIMTd6TTQxIDBoNnYxSDQxek0xNiAxaDEwdjFIMTZ6TTM4IDFoMTB2MUgzOHpNMTUgMmgxMnYxSDE1ek0zNyAyaDEydjFIMzd6TTEwIDNoN3YxSDEwek0yMyAzaDZ2MUgyM3pNMzUgM2g2djFIMzV6TTQ3IDNoN3YxSDQ3ek0xMCA0aDZ2MUgxMHpNMjYgNGg1djFIMjZ6TTMzIDRoNXYxSDMzek00OCA0aDZ2MUg0OHpNMTAgNWg1djFIMTB6TTI3IDVoMTB2MUgyN3pNNDkgNWg1djFINDl6TTcgNmg4djFIN3pNMjkgNmg2djFIMjl6TTQ5IDZoOHYxSDQ5ek03IDdoNHYxSDd6TTMxIDdoMnYxSDMxek01MyA3aDR2MUg1M3pNNyA4aDR2MUg3ek01MyA4aDR2MUg1M3pNNyA5aDR2MUg3ek01MyA5aDR2MUg1M3pNNyAxMGg0djFIN3pNNTMgMTBoNHYxSDUzek03IDExaDR2MUg3ek01MyAxMWg0djFINTN6TTcgMTJoMnYxSDd6TTU1IDEyaDJ2MUg1NXpNNyAxM2gydjFIN3pNMjMgMTNoNHYxSDIzek0zNyAxM2g0djFIMzd6TTU1IDEzaDJ2MUg1NXpNNCAxNGgydjFINHpNNyAxNGgydjFIN3pNMTAgMTRoMnYxSDEwek0yMiAxNGg2djFIMjJ6TTM2IDE0aDZ2MUgzNnpNNTIgMTRoMnYxSDUyek01NSAxNGgydjFINTV6TTU4IDE0aDJ2MUg1OHpNNCAxNWgydjFINHpNNyAxNWgydjFIN3pNMTAgMTVoMnYxSDEwek0yMSAxNWg4djFIMjF6TTM1IDE1aDh2MUgzNXpNNTIgMTVoMnYxSDUyek01NSAxNWgydjFINTV6TTU4IDE1aDJ2MUg1OHpNMSAxNmgydjFIMXpNNCAxNmgydjFINHpNNyAxNmgydjFIN3pNMTAgMTZoMnYxSDEwek0xMyAxNmgydjFIMTN6TTIxIDE2aDJ2MUgyMXpNMjcgMTZoMnYxSDI3ek0zNSAxNmgydjFIMzV6TTQxIDE2aDJ2MUg0MXpNNDkgMTZoMnYxSDQ5ek01MiAxNmgydjFINTJ6TTU1IDE2aDJ2MUg1NXpNNTggMTZoMnYxSDU4ek02MSAxNmgydjFINjF6TTEgMTdoMnYxSDF6TTQgMTdoMnYxSDR6TTcgMTdoMnYxSDd6TTEwIDE3aDJ2MUgxMHpNMTMgMTdoMnYxSDEzek0yMSAxN2gydjFIMjF6TTI3IDE3aDJ2MUgyN3pNMzUgMTdoMnYxSDM1ek00MSAxN2gydjFINDF6TTQ5IDE3aDJ2MUg0OXpNNTIgMTdoMnYxSDUyek01NSAxN2gydjFINTV6TTU4IDE3aDJ2MUg1OHpNNjEgMTdoMnYxSDYxek0xIDE4aDJ2MUgxek00IDE4aDJ2MUg0ek03IDE4aDJ2MUg3ek0xMCAxOGgydjFIMTB6TTEzIDE4aDJ2MUgxM3pNMjIgMThoMnYxSDIyek0yNiAxOGgydjFIMjZ6TTM2IDE4aDJ2MUgzNnpNNDAgMThoMnYxSDQwek00OSAxOGgydjFINDl6TTUyIDE4aDJ2MUg1MnpNNTUgMThoMnYxSDU1ek01OCAxOGgydjFINTh6TTYxIDE4aDJ2MUg2MXpNMSAxOWgydjFIMXpNNCAxOWgydjFINHpNNyAxOWgydjFIN3pNMTAgMTloMnYxSDEwek0xMyAxOWgydjFIMTN6TTIzIDE5aDR2MUgyM3pNMzcgMTloNHYxSDM3ek00OSAxOWgydjFINDl6TTUyIDE5aDJ2MUg1MnpNNTUgMTloMnYxSDU1ek01OCAxOWgydjFINTh6TTYxIDE5aDJ2MUg2MXpNMSAyMGgydjFIMXpNNCAyMGgydjFINHpNNyAyMGgydjFIN3pNMTAgMjBoMnYxSDEwek0xMyAyMGgydjFIMTN6TTIxIDIwaDd2MUgyMXpNMzYgMjBoN3YxSDM2ek00OSAyMGgydjFINDl6TTUyIDIwaDJ2MUg1MnpNNTUgMjBoMnYxSDU1ek01OCAyMGgydjFINTh6TTYxIDIwaDJ2MUg2MXpNMSAyMWgydjFIMXpNNCAyMWgydjFINHpNNyAyMWgydjFIN3pNMTAgMjFoMnYxSDEwek0xMyAyMWgydjFIMTN6TTIwIDIxaDEwdjFIMjB6TTM0IDIxaDEwdjFIMzR6TTQ5IDIxaDJ2MUg0OXpNNTIgMjFoMnYxSDUyek01NSAyMWgydjFINTV6TTU4IDIxaDJ2MUg1OHpNNjEgMjFoMnYxSDYxek0xIDIyaDJ2MUgxek00IDIyaDJ2MUg0ek03IDIyaDJ2MUg3ek0xMCAyMmgydjFIMTB6TTEzIDIyaDJ2MUgxM3pNMjAgMjJoMTB2MUgyMHpNMzQgMjJoMTB2MUgzNHpNNDkgMjJoMnYxSDQ5ek01MiAyMmgydjFINTJ6TTU1IDIyaDJ2MUg1NXpNNTggMjJoMnYxSDU4ek02MSAyMmgydjFINjF6TTQgMjNoMnYxSDR6TTcgMjNoMnYxSDd6TTEwIDIzaDJ2MUgxMHpNMjAgMjNoMTB2MUgyMHpNMzQgMjNoMTB2MUgzNHpNNTIgMjNoMnYxSDUyek01NSAyM2gydjFINTV6TTU4IDIzaDJ2MUg1OHpNNCAyNGgydjFINHpNNyAyNGgydjFIN3pNMTAgMjRoMnYxSDEwek01MiAyNGgydjFINTJ6TTU1IDI0aDJ2MUg1NXpNNTggMjRoMnYxSDU4ek03IDI1aDJ2MUg3ek01NSAyNWgydjFINTV6TTcgMjZoMnYxSDd6TTU1IDI2aDJ2MUg1NXpNNyAyN2g0djFIN3pNNTMgMjdoNHYxSDUzek03IDI4aDR2MUg3ek01MyAyOGg0djFINTN6TTcgMjloNHYxSDd6TTUzIDI5aDR2MUg1M3pNNyAzMGg0djFIN3pNNTMgMzBoNHYxSDUzek03IDMxaDR2MUg3ek01MyAzMWg0djFINTN6TTcgMzJoMTd2MUg3ek00MCAzMmgxN3YxSDQwek05IDMzaDE4djFIOXpNMzcgMzNoMTh2MUgzN3pNOSAzNGgyMHYxSDl6TTM1IDM0aDIwdjFIMzV6TTI0IDM1aDV2MUgyNHpNMzUgMzVoNXYxSDM1ek0yNiAzNmgxMnYxSDI2ek0yOCAzN2g4djFIMjh6TTI4IDM4aDh2MUgyOHoiLz48cGF0aCBmaWxsPSIjMWZlNWM4IiBkPSJNMTcgM2g2djFIMTd6TTQxIDNoNnYxSDQxek0xNiA0aDEwdjFIMTZ6TTM4IDRoMTB2MUgzOHpNMTUgNWgxMnYxSDE1ek0zNyA1aDEydjFIMzd6TTE1IDZoMnYxSDE1ek0yMyA2aDZ2MUgyM3pNMzUgNmg2djFIMzV6TTQ3IDZoMnYxSDQ3ek0xMSA3aDV2MUgxMXpNMjYgN2g1djFIMjZ6TTMzIDdoNXYxSDMzek00OCA3aDV2MUg0OHpNMTEgOGg0djFIMTF6TTI3IDhoMTB2MUgyN3pNNDkgOGg0djFINDl6TTExIDloNHYxSDExek0xOSA5aDR2MUgxOXpNMjkgOWg2djFIMjl6TTQxIDloNHYxSDQxek00OSA5aDR2MUg0OXpNMTEgMTBoNHYxSDExek0xOCAxMGg4djFIMTh6TTMxIDEwaDJ2MUgzMXpNMzggMTBoOHYxSDM4ek00OSAxMGg0djFINDl6TTExIDExaDR2MUgxMXpNMTggMTFoOXYxSDE4ek0zNyAxMWg5djFIMzd6TTQ5IDExaDR2MUg0OXpNMTEgMTJoNHYxSDExek0xOCAxMmgxMXYxSDE4ek0zNSAxMmgxMXYxSDM1ek00OSAxMmg0djFINDl6TTExIDEzaDR2MUgxMXpNMTggMTNoNXYxSDE4ek0yNyAxM2g0djFIMjd6TTMzIDEzaDR2MUgzM3pNNDEgMTNoNXYxSDQxek00OSAxM2g0djFINDl6TTEyIDE0aDN2MUgxMnpNMTggMTRoNHYxSDE4ek0yOCAxNGg4djFIMjh6TTQyIDE0aDR2MUg0MnpNNDkgMTRoM3YxSDQ5ek0xMiAxNWgzdjFIMTJ6TTE4IDE1aDN2MUgxOHpNMjkgMTVoNnYxSDI5ek00MyAxNWgzdjFINDN6TTQ5IDE1aDN2MUg0OXpNMTIgMTZoMXYxSDEyek0xOCAxNmgzdjFIMTh6TTI5IDE2aDZ2MUgyOXpNNDMgMTZoM3YxSDQzek01MSAxNmgxdjFINTF6TTEyIDE3aDF2MUgxMnpNMTggMTdoM3YxSDE4ek0yOSAxN2g2djFIMjl6TTQzIDE3aDN2MUg0M3pNNTEgMTdoMXYxSDUxek0xMiAxOGgxdjFIMTJ6TTE4IDE4aDR2MUgxOHpNMjggMThoOHYxSDI4ek00MiAxOGg0djFINDJ6TTUxIDE4aDF2MUg1MXpNMTIgMTloMXYxSDEyek0xOCAxOWg1djFIMTh6TTI3IDE5aDEwdjFIMjd6TTQxIDE5aDV2MUg0MXpNNTEgMTloMXYxSDUxek0xMiAyMGgxdjFIMTJ6TTE4IDIwaDN2MUgxOHpNMjggMjBoOHYxSDI4ek00MyAyMGgzdjFINDN6TTUxIDIwaDF2MUg1MXpNMTIgMjFoMXYxSDEyek0xOCAyMWgydjFIMTh6TTMwIDIxaDR2MUgzMHpNNDQgMjFoMnYxSDQ0ek01MSAyMWgxdjFINTF6TTEyIDIyaDF2MUgxMnpNMTggMjJoMnYxSDE4ek0zMCAyMmg0djFIMzB6TTQ0IDIyaDJ2MUg0NHpNNTEgMjJoMXYxSDUxek0xMiAyM2gzdjFIMTJ6TTE4IDIzaDJ2MUgxOHpNMzAgMjNoNHYxSDMwek00NCAyM2gydjFINDR6TTQ5IDIzaDN2MUg0OXpNMTIgMjRoM3YxSDEyek0xOCAyNGgyOHYxSDE4ek00OSAyNGgzdjFINDl6TTExIDI1aDR2MUgxMXpNMTggMjVoMjh2MUgxOHpNNDkgMjVoNHYxSDQ5ek0xMSAyNmg0djFIMTF6TTI1IDI2aDE0djFIMjV6TTQ5IDI2aDR2MUg0OXpNMTEgMjdoNXYxSDExek0yNyAyN2gxMHYxSDI3ek00OCAyN2g1djFINDh6TTExIDI4aDZ2MUgxMXpNMjkgMjhoNnYxSDI5ek00NyAyOGg2djFINDd6TTExIDI5aDE0djFIMTF6TTMxIDI5aDJ2MUgzMXpNMzkgMjloMTR2MUgzOXpNMTEgMzBoMTZ2MUgxMXpNMzcgMzBoMTZ2MUgzN3pNMTEgMzFoMTh2MUgxMXpNMzUgMzFoMTh2MUgzNXpNMjQgMzJoN3YxSDI0ek0zMyAzMmg3djFIMzN6TTI3IDMzaDEwdjFIMjd6TTI5IDM0aDZ2MUgyOXpNMjkgMzVoNnYxSDI5eiIvPjwvc3ZnPg%3D%3D&logoColor=white"/></a>
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

书弈 Agent（Shuyi Agent）是基于 Agent 的多人有声书自动配音工作台，面向中文小说配音制作。v0.4.2 将文本模型统一为 OpenAI SDK 兼容配置，并保证模型结果可以人工修改；运行时不会生成或执行模型返回的 Python 代码。

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
- v1 接口使用 `Authorization: Bearer <SHUYI_API_TOKEN>`；文本模型 API Key 可在前端临时输入，后端只在运行内存中读取，不写入持久化快照。

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
| `SHUYI_TEXT_MODEL_API_KEY` | OpenAI SDK 兼容文本模型密钥，也可在前端临时输入 | 空 |
| `SHUYI_TEXT_MODEL_BASE_URL` | OpenAI SDK 兼容文本模型 Base URL | 空 |
| `SHUYI_TEXT_MODEL_NAME` | OpenAI SDK 兼容文本模型名称 | 空 |
| `VITE_API_BASE_URL` | 前端构建时 API 地址 | 本地为 `/api/v1` |

全部环境变量示例见 `.env.example`。

## GitHub Pages

`.github/workflows/pages.yml` 在 `main` 分支前端文件变化时构建并部署静态站点。先在仓库 Settings > Pages 中选择 GitHub Actions，再按需配置仓库变量 `VITE_API_BASE_URL`。Pages 只托管前端，不提供 FastAPI 或模型服务；生产 API 必须启用 HTTPS、Bearer token 和准确的 CORS 来源。

## CNB 镜像发布模板

`.cnb.yml` 是可移植模板：先运行 CPU 契约测试，再在支持 NVIDIA Container Toolkit 的 GPU runner 上构建 CPU/CUDA 镜像并调用本地 TTS 完成真实音频推理。推理成功后始终推送 `${CNB_COMMIT_SHA}-cpu` 和 `${CNB_COMMIT_SHA}-cuda`；仅在 `CNB_TAG=v0.4.2` 时额外推送不可由普通分支流水线覆盖的 `v0.4.2-cpu` 与 `v0.4.2-cuda`。使用前在 CNB 仓库密钥中配置 registry 凭据和必要的模型 token，并根据实际执行器调整 Docker/GPU 服务声明。该模板不代表项目承诺长期托管任何公共镜像。

## 验证

```bash
uv run pytest -q
npm --prefix frontend test
npm --prefix frontend run build
docker compose -f compose.cpu.yaml config
docker compose -f compose.cuda.yaml config
```

真实 TTS 验收还需要已下载模型、足够内存或显存及一段授权明确的参考音频。
