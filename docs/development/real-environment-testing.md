# 真实环境测试规则

## 原则

本项目涉及模型、TTS、音频和复杂 UI。只看代码或 mock 不能证明完成。任何“可用”“通过”“已完成”的结论都必须有新鲜验证证据。

## 环境

- 项目目录：`/Users/gaojing/Documents/002-研究生/0-个人主页/产品/NovelVoice‑Agent`
- Python 环境管理：uv。
- 前端运行：React + Vite + TypeScript。
- 后端运行：FastAPI。
- 本地 TTS 模型路径通过 `QWEN3_TTS_MODEL_PATH` 设置。
- API key 通过环境变量设置。

## 模型测试

语句划分真实环境测试必须记录：

- provider 名称。
- base_url。
- model。
- 输入段落。
- 原始模型输出。
- repair 后输出。
- JSON schema 结果。
- 文本守恒结果。

不能只记录“模型返回成功”。

## TTS 测试

TTS 真实环境测试至少执行：

```bash
curl http://127.0.0.1:7811/health
```

以及一次 `/v1/audio/speech` 或 `/v1/audio/speech/upload` 请求。

必须记录：

- 服务启动命令。
- `QWEN3_TTS_MODEL_PATH`。
- device。
- request text。
- reference audio。
- reference text。
- 输出音频路径。
- 文件大小。
- ffprobe 时长。
- 是否可解码。

## UI 测试

UI 真实环境测试必须保存：

- 导入小说后的章节列表截图。
- 章节正文段落截图。
- 段落确认前后按钮状态截图。
- 语句划分结果截图。
- 角色卡变化后子语句选择器同步截图。
- 音频生成组件截图。

## 音频样本测试

音频样本验收必须检查：

- manifest 记录完整。
- 本地文件存在。
- transcript 存在。
- `ffprobe` 可读取。
- 时长大于 0。
- 许可证允许当前仓库使用方式。

## 不允许的结论

- “看起来能跑”。
- “mock 通过，所以真实服务可用”。
- “文件存在，所以音频可用”。
- “模型输出了一段 JSON，所以划分正确”。
- “下载链接可访问，所以许可证合格”。

