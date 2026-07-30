# Qwen3-TTS 本地服务

本目录放置 v0.12 默认本地 TTS 服务脚本。

## 来源

脚本从本机现有项目复制并改名：

- 原路径：`/Users/gaojing/Documents/002-研究生/993-其他/微信小程序/app_mac/script/qwen3_tts_server.py`
- 当前路径：`backend/tts/qwen3_tts_server.py`

## 默认模型和环境

- Base 模型路径：`/Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-Base`
- VoiceDesign 模型路径：`/Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign`
- Python 环境：`/Users/gaojing/Documents/002-研究生/993-其他/微信小程序/app_mac/.venv-qwen3-tts`
- 默认端口：`7811`

## 启动示例

```bash
/Users/gaojing/Documents/002-研究生/993-其他/微信小程序/app_mac/.venv-qwen3-tts/bin/python \
  backend/tts/qwen3_tts_server.py \
  --model-path /Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-Base \
  --voice-design-model-path /Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  --device cpu
```

## 验证

```bash
curl http://127.0.0.1:7811/health
```

语音合成请求格式见 `spec/audio-synthesis-contract.md`。
