# NovelVoice-Agent

小说辅助生成故事配音的 agent 项目。

v0.3.2 修复 AI角色匹配两类回归：引号后“佩罗恼火道”这类说话动作片段在 AI语句划分后必须归旁白，删除单个段落时只移除该段语句缓存并保留其他段落的 AI角色匹配结果。

## 当前状态

- 规格和验收文档已在 `spec/` 与 `docs/` 中建立，当前版本目标以 `spec/v0.32-harness.md` 和 `docs/development/v0.32-verification.md` 为增量验收。
- 样本小说和可再分发音频素材在 `assets/samples/`；真实本地测试样本默认位于 `/Users/gaojing/Downloads/真实测试样本`。
- 本地 Qwen3-TTS 服务脚本在 `backend/tts/qwen3_tts_server.py`。
- 前端 React + Vite 工作台在 `frontend/`，后端 FastAPI 边界在 `backend/app/api/app.py`。
- 子 Agent 角色配置在 `.codex/agents/`。

## 入口

AI worker 进入仓库后先读：

1. `AGENTS.md`
2. `docs/development/acceptance-standard.md`
3. 当前任务相关 `spec/*.md`，本次 v0.3.2 增量默认参考现有 harness 文档和用户需求
4. `docs/experience-library/active-rules.md`

## 验证

```bash
python3 scripts/validate_harness.py
```

该脚本检查 harness 文件、docs 索引、manifest 和入库样本音频解码；真实 UI、模型和 TTS 仍需按 `docs/development/real-environment-testing.md` 取证。
