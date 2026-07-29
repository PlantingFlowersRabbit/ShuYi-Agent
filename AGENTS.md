# AGENTS.md

## 目标

NovelVoice-Agent 是一个小说辅助生成故事配音的 agent 项目。v0.1 先交付人工主导的人机协作版：导入固定格式 txt 小说，按章节和段落拆分，维护角色卡片，人工确认段落无误后调用小模型做语句划分，再由用户校正角色、情绪、语速、音量和声音模式，最后调用本地 TTS 服务试听或生成音频。

本仓库的 harness 目标不是一次性自动化全流程，而是让后续 AI worker 能稳定理解项目边界、测试口径、资源来源、模型合约和人机协作流程，避免未来接入更强自动化或 harness 工程时大规模推倒重来。

## 仓库结构

- `spec/`：当前版本目标、产品范围、架构边界、LLM 语句划分合约和音频合成合约。
- `assets/`：测试验收素材、素材来源、许可证和资源使用说明。
- `assets/samples/novels/`：小型小说 txt 样本，用于章节和段落正则测试。
- `assets/samples/voices/`：小型可再分发参考音频样本，用于 voice cloning 烟测。
- `backend/`：后续 FastAPI 后端代码目录。v0.1 文档阶段只允许放 TTS 服务脚本和说明，不写核心业务实现。
- `frontend/`：后续 React + Vite + TypeScript 前端代码目录。本轮不创建功能代码。
- `scripts/`：后续下载、资源校验、测试辅助脚本目录。
- `models/`：本地模型说明或 gitignored symlink，不能提交大型模型权重。
- `outputs/`：合成音频和验收输出目录，默认不提交生成产物。
- `docs/`：项目开发文档。新增文档必须更新 `docs/index.md`。
- `docs/development/`：验收标准、测试策略和真实环境测试规则。
- `docs/experience-library/`：开发经验、已解决问题、复发规则和主动规则。
- `.codex/agents/`：固定子 Agent 角色配置。

## 实现约束

- v0.1 是人工主导版本，不实现全自动 harness 编排，不自动批量生成整章音频，不自动替用户确认段落或语句划分。
- 前端默认使用 React + Vite + TypeScript；后端默认使用 Python + FastAPI + uv。
- 模型调用必须通过 OpenAI-compatible provider registry，不能把 `base_url`、模型名、API key 和超时重试策略散落到 UI 或业务代码里。
- 语句划分默认 provider 为 SiliconFlow：`base_url="https://api.siliconflow.cn/v1"`，`model="Qwen/Qwen3-8B"`。
- 未来 harness 自动化 provider 预留 DeepSeek：`base_url="https://api.deepseek.com"`，`model="deepseek-v4-flash"`。v0.1 只保留配置与文档接口。
- TTS 默认优先使用本地 Qwen3-TTS 服务，服务脚本见 `backend/tts/qwen3_tts_server.py`；模型权重通过本机路径或 gitignored symlink 引用，不提交到仓库。
- API key 只通过 `.env`、系统环境变量或本地密钥管理注入，禁止写入文档、测试夹具和样例配置。
- Common Voice 中国大陆中文数据只作为可选本地下载来源记录，不提交原始 clips。
- 任何音频、文本或图片入库前必须有许可证和来源记录。没有许可证的素材不得作为默认样本。
- 所有“模型输出”都必须可人工覆盖；UI 不得把模型结果视为不可修改事实。
- 不为了让测试通过降低验收标准、删除失败用例或绕开文本守恒检查。

## 子 Agent 协作

子 Agent 使用规则见 `docs/subagent-guide.md`；写代码的 AI 和挑毛病的 AI 分离规则见 `docs/builder-reviewer-separation.md`。

本项目默认使用 `.codex/agents/` 下的固定角色：

- `builder`：根据主 Agent 指定范围写实现，可改代码和必要工具，不改验收标准，不做复核。
- `test-author`：根据验收标准写或维护测试，不写产品实现代码。
- `acceptance-checker`：只核对每条验收标准是否都有真实测试覆盖，不写代码、不写测试。
- `visual-reviewer`：对照真实运行截图或录屏做只读视觉验收，不写代码、不修 UI。
- `audio-reviewer`：只读核对音频样本、参考文本、TTS 输出、许可证和声学证据，不写代码、不改音频。
- `reviewer`：开发完成后只读复核，先核对验收标准，再看代码质量和架构边界。

同一轮任务里，写实现的 Agent 不能担任 `reviewer`、`visual-reviewer`、`audio-reviewer` 或 `acceptance-checker`。写实现的 Agent 也不能修改验收标准或测试口径，除非用户明确要求。

派发子 Agent 前，主 Agent 必须给出 spec、验收标准、测试入口、允许读写范围和返回要求。

## 必须严格遵守的开发流程

1. 主 Agent 先读取 `docs/development/acceptance-standard.md`，并把它作为当前验收标准。验收标准缺失、冲突或待定时，先停下来请用户确认。
2. 由 `test-author` 根据验收标准设计详细测试用例或维护测试入口，输出到 `docs/` 或测试目录。
3. 由 `acceptance-checker` 核对每条验收标准是否都有真实测试覆盖；没有覆盖完整时回到第 2 步。
4. 设计和开发测试所依赖的观测工具，包括日志、API 状态、JSON 校验、文本守恒报告、截图、音频文件元数据或可复现操作步骤。
5. 根据 spec 开发实现，可由 `builder` 承担。实现 Agent 不修改验收标准、测试口径和事实源。
6. 在真实环境运行测试和检查；涉及模型或 TTS 的验收必须使用真实 provider 或明确标注的本地替身。
7. 如果改动涉及 UI、布局、交互或可见状态，测试通过后交给独立 `visual-reviewer` 只读复核。
8. 如果改动涉及参考音频、音频生成、TTS 服务、声音复刻或声音设计，测试通过后交给独立 `audio-reviewer` 只读复核。
9. 视觉或音频复核不通过时，记录失败原因，必要时更新 `docs/experience-library/`，修复后回到第 6 步。
10. 测试通过且必要的视觉、音频复核通过后，交给独立 `reviewer` 做综合复核。
11. `reviewer` 不通过时，记录失败原因，必要时更新经验库，修复后回到第 6 步。
12. 只有测试通过、必要的视觉复核通过、必要的音频复核通过、`reviewer` 通过、主 Agent 复核通过，才视为开发完成。

