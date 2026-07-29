# v0.1 测试策略

## 目标

把 `docs/development/acceptance-standard.md` 中的 AC 转成可执行测试、可观察证据或人工复核清单。

## 自动测试优先级

### 单元测试

- 章节正则：给定 `assets/samples/novels/hongloumeng_pg24264_excerpt.txt`，能识别章节标题。
- 段落正则：能按空行或固定格式拆段，不吞文本。
- LLM JSON schema：缺字段、错类型、非法枚举都失败。
- 文本守恒：原段落与 utterances 拼接归一化后必须相等。
- provider registry：SiliconFlow 和 DeepSeek 预留配置能被解析。
- TTS request：voice cloning 和 voice design 的必填字段检查。
- manifest：本地资源路径存在、许可证字段完整、Common Voice 不出现在本地文件列表。

### 集成测试

- 导入小说到章节列表。
- 选择章节到段落模块。
- 确认段落后启用语句划分。
- 模型输出经 JSON repair 和文本守恒校验。
- 子语句角色选择器跟随角色卡变化。
- 单条 utterance 发起 TTS 试听并记录 VoiceJob。

### E2E / 真实环境测试

- 前端 Playwright：两栏布局、章节选择、段落折叠、删除、编辑、确认门禁。
- 后端真实 API：解析、角色、语句划分、TTS 请求。
- 本地 TTS：启动服务，检查 `/health`，生成可解码 wav。
- 音频取证：保存 ffprobe 输出、文件大小、时长和路径。

## 人工复核

人工复核适用于：

- 视觉布局是否符合两栏工作台。
- 模型划分是否达到可校正草稿质量。
- 声音是否足以用于功能烟测。
- 默认角色音频是否明确标注占位。

人工复核必须留下：

- 截图或录屏。
- 输入文件和选择章节。
- 运行命令。
- 观察结论。
- 未通过项。

## 覆盖映射要求

`test-author` 写测试时，每条用例必须标注覆盖的 AC 编号。

`acceptance-checker` 核对时，必须输出：

- AC 编号。
- 对应测试或人工检查点。
- 覆盖状态：已覆盖 / 假覆盖 / 未覆盖 / 覆盖存疑。
- 缺口清单。

