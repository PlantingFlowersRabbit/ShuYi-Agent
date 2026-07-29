# Experience Library

经验库用于把已解决问题沉淀成后续 Agent 能复用的规则。

## 文件

- `active-rules.md`：开发前必须主动遵守的短规则。
- `lessons.md`：完整经验记录，包括现象、原因、修复、验证和下次规则。

## 什么时候更新

以下情况必须更新经验库：

- 同类错误可能复发。
- 失败来自文档、测试或观测缺失。
- 资源许可证或模型输出校验踩坑。
- 真实环境和 mock 结果不一致。
- reviewer、visual-reviewer 或 audio-reviewer 拦住问题。

## 写法

先把完整记录写入 `lessons.md`，再把可复用短规则提炼到 `active-rules.md`。

