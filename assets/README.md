# 资源说明

本文说明 ShuYi-Agent v0.4.1 的样本资源、许可证边界和新增资源要求。

## 目录

- `assets/samples/manifest.json`：所有样本资源的结构化登记表。
- `assets/samples/LICENSES.md`：样本资源来源和许可证说明。
- `assets/samples/novels/`：小说 txt 样本。
- `assets/samples/voices/`：参考音频样本和对应 transcript。

## 入库规则

任何资源入库前必须满足：

- 有明确 `source_url`。
- 有明确 `license`。
- 有明确 `source_project`。
- 有本地文件路径。
- 音频必须有 transcript 或参考文本。
- manifest 中必须声明 `can_redistribute`。

没有许可证、来源不明、只存在聊天记录里的素材，不得进入默认样本目录。

## 当前样本

- 小说样本：Project Gutenberg `A Dream Of Red Mansions / 紅樓夢`，裁剪为 `assets/samples/novels/hongloumeng_pg24264_excerpt.txt`，用于章节和段落正则测试。
- 音频样本：Wikimedia Commons / Lingua Libre CC0 普通话词条音频 `齐心协力`，原始短音频和 20 秒循环派生版本用于 voice cloning 接口烟测。

## 关于默认音色

v0.4.1 默认角色列表与音色库均为空。仓库内 CC0 音频只用于接口和许可证验证；本地验收请通过 `SHUYI_REAL_VOICE_ROOT` 指向授权的参考音频目录，不在代码或文档中写入宿主机绝对路径。

正式测试角色音频应逐步替换为：

- 15-25 秒自然人声。
- 清晰普通话。
- 低噪声。
- 有完整参考文本。
- 可再分发或仅本地使用的授权状态明确。

## Common Voice

Mozilla Common Voice Chinese (China) 可作为本地手工下载的大规模候选语音来源，但本仓库不提交其原始 clips。原因：数据页面同时标注 CC0，并写明禁止重新托管、转售或重新分享数据集。

## LibriVox

LibriVox 录音是美国公有领域，可作为后续更长中文参考音频来源。当前 Archive.org 下载在本环境中连接失败，因此本轮仅在 manifest 中保留为可选来源，不把未下载成功的文件登记为本地样本。
