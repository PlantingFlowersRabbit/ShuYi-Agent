# LLM 语句划分合约

## 目标

把一个已由用户确认的段落拆成用于故事配音的子语句，区分旁白和人物对话。模型输出只作为草稿，必须保留人工校正入口。

## 默认模型

- Provider：SiliconFlow。
- Base URL：`https://api.siliconflow.cn/v1`。
- Model：`Qwen/Qwen3-8B`。
- 接口：OpenAI-compatible chat completions。
- 默认 extra body：`{"enable_thinking": false}`，除非测试证明打开 thinking 更稳定。

## 输入

```json
{
  "chapter_title": "第一回 甄士隱夢幻識通靈 賈雨村風塵懷閨秀",
  "paragraph_id": "p-0001",
  "paragraph_text": "原段落文本",
  "known_roles": [
    {
      "role_id": "narrator",
      "name": "旁白",
      "description": "叙述者"
    }
  ]
}
```

## 输出

模型必须输出严格 JSON，不允许 Markdown、解释文字或代码围栏：

```json
{
  "paragraph_id": "p-0001",
  "utterances": [
    {
      "utterance_id": "p-0001-u-001",
      "speaker_name": "旁白",
      "speaker_role_id": "narrator",
      "voice_mode": "voice_cloning",
      "text": "子语句文本",
      "emotion": "neutral",
      "speed": 1.0,
      "volume": 1.0,
      "design_prompt": null,
      "confidence": 0.8,
      "needs_human_review": false
    }
  ]
}
```

## 字段规则

- `utterance_id`：段落内稳定 ID，格式为 `{paragraph_id}-u-{001}`。
- `speaker_name`：模型判断的说话人名称。未知人物可写原文称呼或 `未知角色`。
- `speaker_role_id`：命中已知角色时填对应 ID；未命中时为 `null`。
- `voice_mode`：只能是 `voice_cloning` 或 `voice_design`。
- `text`：配音文本，不得改写、总结或删减原文。
- `emotion`：默认 `neutral`，可选值由后续 TTS 模型能力配置决定。
- `speed`：默认 `1.0`，合法范围暂定 `0.5` 到 `2.0`。
- `volume`：默认 `1.0`，合法范围暂定 `0.0` 到 `2.0`。
- `design_prompt`：voice design 时必填；voice cloning 时为 `null`。
- `confidence`：`0.0` 到 `1.0`。
- `needs_human_review`：模型不确定、角色未知、文本边界可能错、或者需要声音设计 prompt 时为 `true`。

## 文本守恒

语句划分必须通过文本守恒校验：

1. 取原段落文本。
2. 取所有 `utterances[].text` 按顺序拼接。
3. 对两者做归一化：去除空白、统一中英文引号、统一省略号、统一破折号。
4. 归一化后必须完全相等。

不满足文本守恒时，系统必须：

- 标记该段落为划分失败。
- 保留原始模型输出供调试。
- 不覆盖用户现有人工编辑内容。
- 提供“重试划分”和“手动编辑”入口。

## Prompt 约束

提示词必须强调：

- 不得改写原文。
- 不得总结。
- 不得自行补充角色。
- 只拆分说话归属和配音粒度。
- 输出严格 JSON。
- 如果角色不确定，保留 `speaker_role_id=null` 且 `needs_human_review=true`。

## Repair 规则

如果模型输出不是合法 JSON，最多允许一次 JSON repair。repair 后仍失败，必须把段落标记为失败，不得猜测补齐。

如果 JSON 合法但文本不守恒，不允许通过简单删除或硬塞文本让测试过关；必须重新划分或交给人工。

