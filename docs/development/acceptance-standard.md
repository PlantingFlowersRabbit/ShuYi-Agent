# NovelVoice-Agent v0.12 验收标准

## 总通过口径

v0.12 通过验收，需要同时满足：

- 文档、spec、资源说明、agent 配置完整。
- 人工协作主流程范围清楚，不混入全自动 harness 编排。
- 主页面、音色资源库和模型配置三个页面可运行。
- 资源有来源和许可证。
- 模型输出有 JSON schema、repair 和文本守恒校验。
- UI、LLM、TTS 和音频验收都能在真实环境取证。

## 一、仓库和文档

- **AC-DOC-01** 仓库包含 `AGENTS.md`，并说明目标、结构、实现约束、子 Agent 协作和强制开发流程。
- **AC-DOC-02** 仓库包含兼容入口 `AGENT.md`，并指向 `AGENTS.md`。
- **AC-DOC-03** `spec/` 包含 v0.12 版本目标、产品范围、架构合约、LLM 合约和 TTS 合约。
- **AC-DOC-04** `docs/index.md` 包含所有新增 docs 文档链接。
- **AC-DOC-05** `docs/experience-library/` 包含入口、主动规则和 lessons。
- **AC-DOC-06** `.codex/agents/` 包含 builder、test-author、acceptance-checker、visual-reviewer、audio-reviewer 和 reviewer。

## 二、产品流程

- **AC-FLOW-01** v0.12 明确是人工主导的人机协作版。
- **AC-FLOW-02** txt 小说导入后按中文章节或数字编号章节正则拆分。
- **AC-FLOW-03** 章节选择后右侧展示该章节正文。
- **AC-FLOW-04** 正文按段落拆成可折叠、可编辑、可删除模块。
- **AC-FLOW-05** 段落确认前不能执行语句划分。
- **AC-FLOW-06** 段落确认后才出现或启用语句划分按钮。
- **AC-FLOW-07** 语句划分结果必须嵌套在来源段落内，且可人工编辑。
- **AC-FLOW-08** 角色卡变更后，子语句角色选择器同步更新。
- **AC-FLOW-09** 主页面 UI 参考 Unitale 浅色工作台风格，不出现明显文本重叠或按钮溢出。
- **AC-FLOW-10** 主页面必须展示上传小说、章节划分、语句划分和语音生成四个进度条。
- **AC-FLOW-11** 上传大体量小说后，左侧小说章节区不得渲染完整小说正文，只展示开头预览，并保留完整文本用于章节划分。
- **AC-FLOW-12** 点击“划分章节”之前，右侧不得渲染具体章节内容；选择某个章节后才加载并拆分该章正文。
- **AC-FLOW-13** 左侧和右侧工作区必须使用独立纵向滚动条，不把整个页面作为主要滚动容器。

## 三、角色和声音

- **AC-ROLE-01** 默认角色列表由音色资源库驱动，不再使用三个烟测占位角色卡。
- **AC-ROLE-02** 每个角色卡包含姓名、简介、声音模式、绑定音色、参考音频或声音设计 prompt。
- **AC-ROLE-03** voice cloning 缺少参考音频或参考文本时不得发起 TTS。
- **AC-ROLE-04** voice design 缺少 prompt 时不得发起 TTS。
- **AC-ROLE-05** 角色音色选择器必须展示音色名称，并可查看音色描述和语音具体内容。
- **AC-ROLE-06** 音色资源库必须支持列表、添加、生成、修改、勾选删除和参考音频播放。
- **AC-ROLE-07** 生成音色若使用本地替身，必须标注为替身，不得宣称真实 voice design 质量。

## 四、LLM 语句划分

- **AC-LLM-01** 默认语句划分 provider 为 SiliconFlow `Qwen/Qwen3-8B`。
- **AC-LLM-02** 模型输出必须是严格 JSON。
- **AC-LLM-03** 每个 utterance 包含 `utterance_id`、`speaker_name`、`speaker_role_id`、`voice_mode`、`text`、`emotion`、`speed`、`volume`、`design_prompt`、`confidence`、`needs_human_review`。
- **AC-LLM-04** 语句划分必须通过文本守恒校验。
- **AC-LLM-05** JSON repair 最多一次；repair 后仍失败必须标记失败，不得猜测补齐。
- **AC-LLM-06** 角色不确定时必须 `speaker_role_id=null` 且 `needs_human_review=true`。
- **AC-LLM-07** 不得为了通过文本守恒测试改写、总结、删除或新增原文。

## 五、TTS 和音频

- **AC-AUDIO-01** 本地 Qwen3-TTS 服务脚本复制到 `backend/tts/qwen3_tts_server.py`。
- **AC-AUDIO-02** 大型 TTS 模型权重不得提交到仓库。
- **AC-AUDIO-03** TTS 服务必须提供 `/health`。
- **AC-AUDIO-04** TTS 服务必须支持 `/v1/audio/speech` JSON 请求。
- **AC-AUDIO-05** TTS 服务必须支持 `/v1/audio/speech/upload` multipart 请求。
- **AC-AUDIO-06** 生成音频必须非空、可解码、时长大于 0.5 秒。
- **AC-AUDIO-07** 每个 VoiceJob 必须能追溯 utterance、role、provider、参考音频、参考文本和输出路径。
- **AC-AUDIO-08** 音频样本必须有许可证、来源和 transcript。

## 六、资源和许可证

- **AC-ASSET-01** `assets/README.md` 说明资源入库规则。
- **AC-ASSET-02** `assets/READEME.md` 作为兼容指针存在。
- **AC-ASSET-03** `assets/samples/manifest.json` 登记所有本地样本资源。
- **AC-ASSET-04** manifest 每个本地资源包含 source_url、license、source_project、original_filename、clip_range_seconds、transcript、intended_role、can_redistribute。
- **AC-ASSET-05** Common Voice Chinese (China) 只登记为可选本地下载来源，不提交原始 clips。
- **AC-ASSET-06** 没有完整许可证记录的素材不得作为默认样本。

## 七、真实环境和复核

- **AC-REAL-01** 模型、TTS、音频和 UI 验收必须优先在真实环境执行。
- **AC-REAL-02** mock 只能用于单元测试，不得替代端到端结论。
- **AC-REAL-03** UI 改动需要真实截图或录屏证据。
- **AC-REAL-04** 音频改动需要真实音频文件、时长、可解码结果和许可证证据。
- **AC-REAL-05** 开发完成前必须经过 builder / test-author / acceptance-checker / visual-reviewer / audio-reviewer / reviewer 的分离规则，适用者不得由同一上下文兼任。
- **AC-REAL-06** 真实小说样本 `这个地下城长蘑菇了.txt` 必须能按数字编号章节解析。
- **AC-REAL-07** 本地真实音色样本 `年轻男`、`御姐音`、`播音腔女`、`男声旁白` 必须能读取 transcript 并通过 `ffprobe` 解码。

## 八、模型配置

- **AC-CONFIG-01** 模型配置页集中展示 LLM provider、base URL、模型名、API-key 环境变量名、超时和重试。
- **AC-CONFIG-02** 模型配置页集中展示 TTS provider、base URL、模型路径环境变量、device 环境变量和超时。
- **AC-CONFIG-03** API key 只能通过环境变量或本地密钥管理注入，前端代码、文档和测试夹具不得包含真实 key。
