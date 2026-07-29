# 音频合成合约

## 目标

为每条子语句生成可试听音频。v0.1 优先支持 voice cloning；voice design 先保留 UI、prompt 和请求合约，可在后续接入支持声音设计的 provider。

## 声音模式

| 模式 | 输入 | 用途 |
| --- | --- | --- |
| `voice_cloning` | 参考音频 + 参考文本 + 待合成文本 | 已有目标人物录音，希望还原音色 |
| `voice_design` | 声音描述 prompt + 待合成文本 | 没有录音素材，希望根据文字描述生成新音色 |

## 本地 Qwen3-TTS 服务

默认本地服务脚本：

- `backend/tts/qwen3_tts_server.py`

默认外部本机资源：

- 模型路径：`/Users/gaojing/Documents/002-研究生/993-其他/微信小程序/app_mac/models/Qwen3-TTS-12Hz-1.7B-Base`
- Python 环境：`/Users/gaojing/Documents/002-研究生/993-其他/微信小程序/app_mac/.venv-qwen3-tts`
- 原服务脚本：`/Users/gaojing/Documents/002-研究生/993-其他/微信小程序/app_mac/script/qwen3_tts_server.py`

大型模型权重不得提交到本仓库。

## 服务接口

健康检查：

```http
GET /health
```

voice cloning JSON 请求：

```http
POST /v1/audio/speech
Content-Type: application/json
```

```json
{
  "input": "待合成文本",
  "audio_sample": "base64 encoded wav",
  "ref_text": "参考音频对应文本",
  "language": "Chinese",
  "response_format": "wav",
  "x_vector_only": false
}
```

voice cloning multipart 请求：

```http
POST /v1/audio/speech/upload
Content-Type: multipart/form-data
```

字段：

- `input`
- `voice_file`
- `ref_text`
- `language`
- `response_format`
- `x_vector_only`

## VoiceJob 记录

一次 TTS 试听或生成至少记录：

```json
{
  "voice_job_id": "vj-0001",
  "utterance_id": "p-0001-u-001",
  "role_id": "narrator",
  "voice_mode": "voice_cloning",
  "provider": "local-qwen3-tts",
  "request_text": "待合成文本",
  "reference_audio_path": "assets/samples/voices/narrator_baijiaxing_librivox_20s.wav",
  "reference_text": "赵钱孙李，周吴郑王。",
  "response_format": "wav",
  "output_path": "outputs/audio/vj-0001.wav",
  "status": "succeeded",
  "error": null
}
```

## 验收要求

- `/health` 返回可解析 JSON 且 `ok=true` 才能判定服务可用。
- 生成音频必须非空、可解码、时长大于 0.5 秒。
- 输出音频必须能追溯到 utterance、role、reference audio 和 reference text。
- voice cloning 缺少参考音频或参考文本时不得发起请求。
- voice design 缺少 `design_prompt` 时不得发起请求。
- 试听失败必须保留错误信息，不得静默吞掉。

