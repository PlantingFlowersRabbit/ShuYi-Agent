# NovelVoice-Agent

小说辅助生成故事配音的 agent 项目。

v0.1 先落地人工主导的人机协作版 harness：项目目标、规格、验收标准、资源清单、固定子 Agent 角色和本地 TTS 服务脚本。核心前后端功能代码将在后续轮次基于这些规格实现。

## 当前状态

- 规格和验收文档已在 `spec/` 与 `docs/` 中建立。
- 样本小说和 CC0 语音烟测素材在 `assets/samples/`。
- 本地 Qwen3-TTS 服务脚本在 `backend/tts/qwen3_tts_server.py`。
- 子 Agent 角色配置在 `.codex/agents/`。

## 入口

AI worker 进入仓库后先读：

1. `AGENTS.md`
2. `docs/development/acceptance-standard.md`
3. 当前任务相关 `spec/*.md`
4. `docs/experience-library/active-rules.md`

## 验证

```bash
python3 scripts/validate_harness.py
```

该脚本只检查 harness 文件和样本资源，不启动前端、后端或 TTS 服务。

