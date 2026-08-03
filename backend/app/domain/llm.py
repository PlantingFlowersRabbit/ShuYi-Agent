from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable
from typing import Any

HttpPost = Callable[[str, dict[str, str], dict[str, Any], int], dict[str, Any]]
ApiKeyLookup = Callable[[str], str | None]


class MissingProviderCredential(RuntimeError):
    pass


def build_segmentation_messages(
    *,
    chapter_title: str,
    paragraph_id: str,
    paragraph_text: str,
    known_roles: list[dict[str, Any]],
) -> list[dict[str, str]]:
    roles_json = json.dumps(known_roles, ensure_ascii=False, indent=2)
    user_prompt = f"""
请使用已配置的 OpenAI SDK 兼容文本模型，把已由用户确认的小说段落拆成配音子台词。

要求：
- 输出严格 JSON，不允许 Markdown、解释文字或代码围栏。
- 不得改写、总结、删除或新增原文。
- 原段落中单独成行的装饰分隔符（例如“————”“……”）不要作为 utterance 输出。
- text 字段必须从原段落中逐字复制连续片段；中文/英文标点、全角/半角符号、单双引号都不能替换。
- 重点是以说话人/角色为单位划分配音片段，不是按句号机械拆分。
- 双引号通常是区分人物对白与旁白动作的关键。若一段中出现“对白”+叙述动作+“对白”，应拆成三段。
- 示例：`“先别急着走。”林舟停在门口，“我还有一个问题。”` 应拆成：
  1. `“先别急着走。”`
  2. `林舟停在门口，`
  3. `“我还有一个问题。”`
- 若一整段双引号内是同一角色连续说话，例如 `“我知道你还有疑问，但现在最重要的是确认路线，然后一起离开这里。”`，不要再按逗号拆开。
- 如果角色不确定，speaker_role_id 必须为 null，needs_human_review 必须为 true。
- utterance_id 使用 {paragraph_id}-u-001 递增格式。
- text 字段按 utterance 顺序拼接后必须与原段落文本通过文本守恒校验。
- 每个 utterance 必须包含以下全部字段，不得省略：
  utterance_id、speaker_name、speaker_role_id、voice_mode、text、emotion、speed、volume、design_prompt、confidence、needs_human_review。
- speaker_name 使用角色名或“未知角色”；speaker_role_id 只能使用已知角色 role_id 或 null。
- voice_mode 只能是 voice_cloning 或 voice_design；默认使用角色卡 voice_mode，未知角色可用 voice_design。
- voice_design 必须给出 design_prompt；voice_cloning 的 design_prompt 必须为 null。
- emotion 默认 neutral；speed 默认 1.0；volume 默认 1.0；confidence 必须是 0 到 1 的数字。
- 只返回如下结构：
{{
  "paragraph_id": "{paragraph_id}",
  "utterances": [
    {{
      "utterance_id": "{paragraph_id}-u-001",
      "speaker_name": "旁白",
      "speaker_role_id": "narrator",
      "voice_mode": "voice_cloning",
      "text": "原文片段",
      "emotion": "neutral",
      "speed": 1.0,
      "volume": 1.0,
      "design_prompt": null,
      "confidence": 0.9,
      "needs_human_review": false
    }}
  ]
}}

章节标题：{chapter_title}
paragraph_id：{paragraph_id}
已知角色：
{roles_json}

原段落：
{paragraph_text}
""".strip()
    return [
        {
            "role": "system",
            "content": "你是小说配音台词划分助手，只返回符合合约的严格 JSON。",
        },
        {"role": "user", "content": user_prompt},
    ]


def urllib_http_post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


class OpenAICompatibleSegmentationClient:
    def __init__(
        self,
        *,
        provider: dict[str, Any],
        api_key_lookup: ApiKeyLookup = os.environ.get,
        http_post: HttpPost = urllib_http_post,
    ):
        self.provider = provider
        self.api_key_lookup = api_key_lookup
        self.http_post = http_post

    def segment(
        self,
        *,
        chapter_title: str,
        paragraph_id: str,
        paragraph_text: str,
        known_roles: list[dict[str, Any]],
    ) -> str:
        api_key_env = self.provider["api_key_env"]
        api_key = self.api_key_lookup(api_key_env)
        if not api_key:
            raise MissingProviderCredential(f"Missing API key environment variable: {api_key_env}")

        messages = build_segmentation_messages(
            chapter_title=chapter_title,
            paragraph_id=paragraph_id,
            paragraph_text=paragraph_text,
            known_roles=known_roles,
        )
        payload = {
            "model": self.provider["model"],
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if self.provider.get("max_tokens"):
            payload["max_tokens"] = self.provider["max_tokens"]
        payload.update(self.provider.get("extra_body", {}))
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        response = self.http_post(
            f"{self.provider['base_url'].rstrip('/')}/chat/completions",
            headers,
            payload,
            int(self.provider.get("timeout_seconds", 60)),
        )
        return str(response["choices"][0]["message"]["content"])
