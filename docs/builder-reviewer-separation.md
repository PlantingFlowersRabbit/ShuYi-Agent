# 写代码的 AI 与挑毛病的 AI 要分开

## 目标

避免“写实现的 Agent 给自己定标准、写测试、审自己、判自己通过”。本项目用固定角色和外部验收标准把生成者和评估者分离。

## 原则

1. 写代码的 Agent 只按指定范围实现。
2. 测试作者只根据验收标准写测试。
3. 覆盖核对者只判断 AC 是否有真实测试覆盖。
4. 视觉复核者只读查看 UI 证据。
5. 音频复核者只读查看音频证据和许可证。
6. 综合 reviewer 先查规范，再查代码质量。
7. 主 Agent 不能只照搬任何子 Agent 结论，必须做最终复核。

## 为什么有效

角色分离要同时满足三件事：

- 新上下文：reviewer 不继承 builder 的实现思路。
- 对立立场：reviewer 默认挑错，不默认通过。
- 独立标准：reviewer 对照 `docs/development/acceptance-standard.md`，不是临场编标准。

## 落地方式

项目内固定角色放在 `.codex/agents/`：

- `builder.toml`
- `test-author.toml`
- `acceptance-checker.toml`
- `visual-reviewer.toml`
- `audio-reviewer.toml`
- `reviewer.toml`

每个角色都要求主 Agent 提供必要输入。必要输入缺失时，子 Agent 必须停止并返回缺少什么，不得猜路径或跨版本混用标准。

## 不允许

- builder 修改 `docs/development/acceptance-standard.md`。
- builder 删除失败测试。
- reviewer 自动修代码。
- visual-reviewer 用代码推断代替真实截图。
- audio-reviewer 用文件存在代替可解码和许可证检查。
- 主 Agent 在未运行验证前宣称完成。

