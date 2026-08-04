# 书弈 Agent 前端

前端使用 React 19、TypeScript 和 Vite，提供小说导入、角色确认、长句台词拆分、制作任务 Planner、配音编排与结果导出工作台。

## 本地开发

```bash
npm ci
npm run dev
```

默认访问 `http://127.0.0.1:5173`。本地开发时，`/api/v1` 与 `/outputs` 由 Vite 代理到 `http://127.0.0.1:8000`。需要直连其他后端时，在仓库根目录 `.env` 或前端构建环境设置：

```dotenv
VITE_API_BASE_URL=api.example.com
```

不要把 provider 密钥写进 `VITE_*` 变量；它们会进入浏览器静态文件。`VITE_API_BASE_URL` 可填完整 `/api/v1` URL，也可填裸域名。GitHub Pages 或临时 CNB 后端地址变化时，也可以在页面“模型配置 > 后端 API”里直接粘贴新的 FastAPI 地址并保存；这个地址不同于 TTS 模型的 `Base URL`。

CNB/VS Code 环境会通过 `.devcontainer/devcontainer.json` 请求自动转发 8000 端口，并通过 `.vscode/settings.json` 识别启动脚本打印的 `http://localhost:8000`。公网地址以 PORTS 面板的 Forwarded Address 为准，不要使用启动日志里的模板地址。

## 项目工作区与审稿队列

v0.6.1 主页面侧栏新增 **项目工作区**、**质量检查面板** 和 **审稿队列**：

- 项目工作区调用 `/api/v1/projects`，支持新建、打开最近项目和删除非默认项目；最近项目顺序保存在浏览器 `localStorage`。
- 质量检查面板向 `/api/v1/projects/{project_id}/quality-check` 发送当前章节、角色、台词与配音状态，展示生成前检查和导出前检查结果。
- 制作任务 Planner 调用 `/api/v1/projects/{project_id}/planner/plan`、`/planner/execute` 和 `/planner/review`，展示“把当前章节处理到可导出”的计划树、步骤状态、失败原因和恢复建议。
- 审稿队列调用 `/api/v1/projects/{project_id}/review-queue`，集中处理 `needs_human_review`、未选角色、超长台词和配音失败，并提供批量确认、批量改角色、批量拆分超长台词和批量重试入口。

前端只保存最近项目 id 和后端地址等 UI 偏好；项目元数据、输出目录和质量检查结果以后端为准。

## 长句拆分与配音重试

v0.6.6 在审稿队列工具栏新增 **批量拆分超长台词**，在每条台词工具栏新增 **一键拆分长台词** 与 **合并相邻台词**。拆分接口返回后，前端会用稳定台词 ID 找到拆出的片段，并直接加入现有 `dubbingQueueRef` 配音队列；批量重试会先调用 `/api/v1/projects/{project_id}/utterances/retry-queue`，清掉旧失败状态后再生成音频。

批量改角色现在调用 `/api/v1/projects/{project_id}/utterances/bulk-role`，由后端统一更新 `speaker_role_id`、角色名和人工复核状态。前端继续只保存 UI 偏好，不把编辑后的台词状态单独持久化到浏览器。

## Story Bible RAG

v0.6.2 的 Story Memory、Story Bible、embedding 和 Qdrant 能力先落在后端 API：`/api/v1/projects/{project_id}/memory/index`、`/memory/search`、`/story-bible` 和 `/story-bible/facts/{fact_id}`。v0.6.4 追加长期记忆写入、`memory-context` 和 `run-memory` 恢复 API；前端当前不会保存 embedding key 或向量库配置，后续页面只应调用后端聚合结果并展示 `source_citations` 与可信度状态。

## Agent 追踪页面

v0.6.0 顶部导航新增 **Agent追踪**。页面会调用 `/api/v1/agent-runs` 和 `/api/v1/agent-runs/{run_id}`，展示 Run History、Prompt SHA、token 预算、输入摘要、模型输出、JSON 校验、reflection 和最终决策。v0.6.3 追加 Tool Calls 区块，展示工具名、参数摘要、返回摘要、耗时和失败原因。该页面只读取后端 trace，不接收或展示模型 API key。

## 测试与构建

```bash
npm test
npm run build
npm run preview
```

构建产物位于 `dist/`，由 Git 忽略。

## GitHub Pages

仓库工作流 `.github/workflows/pages.yml` 会运行 `npm ci` 和 `npm run build`，Vite 在 GitHub Actions 中根据 `GITHUB_REPOSITORY` 自动设置 `/<仓库名>/` base path。若使用自定义域名或根路径，可设置 `VITE_PAGES_BASE_URL=/`。

Pages 只能部署静态前端。远程 API 必须：

1. 可从公网通过 HTTPS 访问；
2. 在页面“模型配置 > 后端 API”或构建变量 `VITE_API_BASE_URL` 中指向 `/api/v1` 后端；
3. 不在仓库变量或前端 bundle 中暴露模型服务密钥。
