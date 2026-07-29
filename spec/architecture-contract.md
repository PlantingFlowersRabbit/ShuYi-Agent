# 架构合约

## 默认技术栈

- 前端：React + Vite + TypeScript。
- 后端：Python + FastAPI。
- 环境管理：uv。
- 版本控制：git。
- LLM / TTS provider：OpenAI-compatible client shape。

## 未来代码结构

```text
frontend/
  src/
    app/
    features/novel-import/
    features/chapters/
    features/roles/
    features/paragraphs/
    features/utterances/
    features/audio-preview/
    shared/
backend/
  app/
    api/
    core/
    domain/
    providers/
    services/
    schemas/
  tts/
scripts/
models/
outputs/
```

本轮不创建前端和后端业务代码，只用文档锁定边界。

## 模块边界

- 小说解析模块只负责 txt、章节和段落正则，不调用 LLM。
- 角色模块只负责角色卡数据和素材引用，不生成音频。
- 语句划分模块只负责 LLM prompt、JSON schema、repair 和文本守恒校验。
- 音频模块只负责 TTS 请求、输出文件、试听 URL 和音频元数据。
- UI 模块只负责交互和编辑状态，不硬编码 provider 密钥、模型路径或 TTS 细节。
- provider registry 负责 `base_url`、`api_key`、`model`、`timeout`、`max_retries`、`extra_body`。

## Provider Registry 合约

每个 provider 配置必须至少包含：

```json
{
  "name": "siliconflow-qwen3-8b",
  "kind": "chat_completions",
  "base_url": "https://api.siliconflow.cn/v1",
  "model": "Qwen/Qwen3-8B",
  "api_key_env": "SILICONFLOW_API_KEY",
  "timeout_seconds": 60,
  "max_retries": 2,
  "extra_body": {
    "enable_thinking": false
  }
}
```

未来 DeepSeek harness provider 预留：

```json
{
  "name": "deepseek-harness",
  "kind": "chat_completions",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-v4-flash",
  "api_key_env": "DEEPSEEK_API_KEY",
  "timeout_seconds": 120,
  "max_retries": 2,
  "extra_body": {}
}
```

## 本地模型和输出边界

- `models/` 只放说明文件或本地 symlink，不提交大型权重。
- `outputs/` 只放本地生成音频、临时验收输出和报告，默认 gitignore。
- Qwen3-TTS 的模型路径通过 `QWEN3_TTS_MODEL_PATH` 提供。
- Qwen3-TTS 的 Python 环境路径只写在文档和 `.env.example`，不在代码中硬编码为唯一值。

## API 边界

后端 API 后续至少保留这些资源接口：

- `POST /api/novels/parse`
- `GET /api/chapters`
- `GET /api/chapters/{chapter_id}`
- `PATCH /api/paragraphs/{paragraph_id}`
- `POST /api/paragraphs/{paragraph_id}/segment`
- `GET /api/roles`
- `POST /api/roles`
- `PATCH /api/roles/{role_id}`
- `POST /api/utterances/{utterance_id}/speech`

v0.1 实现时可调整路径细节，但不能破坏对象边界。

