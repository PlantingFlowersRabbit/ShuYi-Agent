# NovelVoice-Agent

小说辅助生成故事配音的 agent 项目。

v0.12 聚焦本地 Qwen3-TTS 音色生成和台词生成链路：音色资源库生成音色走 VoiceDesign 模型，台词生成走 Base voice clone 模型，并保留大文本章节懒加载工作台。

## 当前状态

- 规格和验收文档已在 `spec/` 与 `docs/` 中建立，当前版本目标见 `spec/v0.12-harness.md`。
- 样本小说和可再分发音频素材在 `assets/samples/`；真实本地测试样本默认位于 `/Users/gaojing/Downloads/真实测试样本`。
- 本地 Qwen3-TTS 服务脚本在 `backend/tts/qwen3_tts_server.py`。
- 前端 React + Vite 工作台在 `frontend/`，后端 FastAPI 边界在 `backend/app/api/app.py`。
- 子 Agent 角色配置在 `.codex/agents/`。

## 入口

AI worker 进入仓库后先读：

1. `AGENTS.md`
2. `docs/development/acceptance-standard.md`
3. 当前任务相关 `spec/*.md`，v0.12 默认读 `spec/v0.12-harness.md`
4. `docs/experience-library/active-rules.md`

## 验证

```bash
python3 scripts/validate_harness.py
```

该脚本检查 harness 文件、docs 索引、manifest 和入库样本音频解码；真实 UI、模型和 TTS 仍需按 `docs/development/v0.12-verification.md` 取证。
