# NovelVoice-Agent

小说辅助生成故事配音的 agent 项目。

v0.3.3 移除前端独立 `AI语句划分` 入口；`AI角色匹配` 在同一个批量角色匹配 Agent 响应中同时完成必要的语句划分和角色选择。

## 当前状态

- 规格和验收文档已在 `spec/` 与 `docs/` 中建立，当前版本目标以 `spec/v0.33-harness.md` 和 `docs/development/v0.33-verification.md` 为增量验收。
- 样本小说和可再分发音频素材在 `assets/samples/`；真实本地测试样本默认位于 `/Users/gaojing/Downloads/真实测试样本`。
- 本地 Qwen3-TTS 服务脚本在 `backend/tts/qwen3_tts_server.py`。
- 前端 React + Vite 工作台在 `frontend/`，后端 FastAPI 边界在 `backend/app/api/app.py`。
- 子 Agent 角色配置在 `.codex/agents/`。

## 入口

AI worker 进入仓库后先读：

1. `AGENTS.md`
2. `docs/development/acceptance-standard.md`
3. 当前任务相关 `spec/*.md`，本次 v0.3.3 增量默认参考现有 harness 文档和用户需求
4. `docs/experience-library/active-rules.md`

## 验证

```bash
python3 scripts/validate_harness.py
```

该脚本检查 harness 文件、docs 索引、manifest 和入库样本音频解码；真实 UI、模型和 TTS 仍需按 `docs/development/real-environment-testing.md` 取证。
