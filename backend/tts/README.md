# Qwen3-TTS 本地服务

`qwen3_tts_server.py` 提供书翼 Agent 使用的本地语音合成 HTTP 服务，支持声纹复刻与 VoiceDesign。

## 启动

```bash
uv sync --group backend --group tts
uv run python backend/tts/qwen3_tts_server.py \
  --model-path ./models/Qwen3-TTS-12Hz-1.7B-Base \
  --voice-design-model-path ./models/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  --device cpu
```

默认端口为 `7811`，使用 `curl http://127.0.0.1:7811/health` 检查模型是否加载完成。模型权重不得提交到 Git；容器下载与缓存规则见仓库根目录 `README.md`。
