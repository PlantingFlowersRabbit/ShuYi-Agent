# NovelVoice-Agent v0.1 验收标准

## 总通过口径

v0.1 通过验收，需要同时满足：

- 文档、spec、资源说明、agent 配置完整。
- 后续实现能按本文 AC 建立测试和证据。
- 人工协作主流程范围清楚，不混入全自动 harness 编排。
- 资源有来源和许可证。
- 模型输出有 JSON schema、repair 和文本守恒校验。
- UI、LLM、TTS 和音频验收都能在真实环境取证。

## 一、仓库和文档

- **AC-DOC-01** 仓库包含 `AGENTS.md`，并说明目标、结构、实现约束、子 Agent 协作和强制开发流程。
- **AC-DOC-02** 仓库包含兼容入口 `AGENT.md`，并指向 `AGENTS.md`。
- **AC-DOC-03** `spec/` 包含 v0.1 版本目标、产品范围、架构合约、LLM 合约和 TTS 合约。
- **AC-DOC-04** `docs/index.md` 包含所有新增 docs 文档链接。
- **AC-DOC-05** `docs/experience-library/` 包含入口、主动规则和 lessons。
- **AC-DOC-06** `.codex/agents/` 包含 builder、test-author、acceptance-checker、visual-reviewer、audio-reviewer 和 reviewer。

## 二、产品流程

- **AC-FLOW-01** v0.1 明确是人工主导的人机协作版。
- **AC-FLOW-02** txt 小说导入后按固定章节正则拆分。
- **AC-FLOW-03** 章节选择后右侧展示该章节正文。
- **AC-FLOW-04** 正文按段落拆成可折叠、可编辑、可删除模块。
- **AC-FLOW-05** 段落确认前不能执行语句划分。
- **AC-FLOW-06** 段落确认后才出现或启用语句划分按钮。
- **AC-FLOW-07** 语句划分结果必须可人工编辑。
- **AC-FLOW-08** 角色卡变更后，子语句角色选择器同步更新。

## 三、角色和声音

- **AC-ROLE-01** 默认提供旁白、男主、女主三个角色卡。
- **AC-ROLE-02** 每个角色卡包含姓名、简介、声音模式、参考音频或声音设计 prompt。
- **AC-ROLE-03** voice cloning 缺少参考音频或参考文本时不得发起 TTS。
- **AC-ROLE-04** voice design 缺少 prompt 时不得发起 TTS。
- **AC-ROLE-05** 默认样本角色音频必须标注“功能烟测占位，不代表最终音色质量”。

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

