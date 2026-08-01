# 书弈 Agent 前端

前端使用 React 19、TypeScript 和 Vite，提供小说导入、角色确认、配音编排与结果导出工作台。

## 本地开发

```bash
npm ci
npm run dev
```

默认访问 `http://127.0.0.1:5173`。本地开发时，`/api/v1` 与 `/outputs` 由 Vite 代理到 `http://127.0.0.1:8000`。需要直连其他后端时，在仓库根目录 `.env` 或前端构建环境设置：

```dotenv
VITE_API_BASE_URL=api.example.com
```

不要把 provider 密钥写进 `VITE_*` 变量；它们会进入浏览器静态文件。`VITE_API_BASE_URL` 可填完整 `/api/v1` URL，也可填裸域名。

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
2. 将 Pages 域名加入 `SHUYI_CORS_ORIGINS`；
3. 不在仓库变量或前端 bundle 中暴露模型服务密钥。
