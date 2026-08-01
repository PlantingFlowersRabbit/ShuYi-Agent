from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.app.domain.llm import (
    ApiKeyLookup,
    MissingProviderCredential,
    build_segmentation_messages,
)
from backend.app.domain.segmentation import (
    SegmentationValidationResult,
    repair_json_output_once,
    validate_segmentation_result,
)


@dataclass(frozen=True)
class AiSegmentationAgentResult:
    raw_output: str
    validation: SegmentationValidationResult
    reflection_count: int
    trace: list[str]


class LangChainSegmentationSkill:
    def __init__(
        self,
        *,
        provider: dict[str, Any],
        api_key_lookup: ApiKeyLookup,
    ):
        self.provider = provider
        self.api_key_lookup = api_key_lookup

    def segment(
        self,
        *,
        chapter_title: str,
        paragraph_id: str,
        paragraph_text: str,
        known_roles: list[dict[str, Any]],
    ) -> str:
        messages = build_segmentation_messages(
            chapter_title=chapter_title,
            paragraph_id=paragraph_id,
            paragraph_text=paragraph_text,
            known_roles=known_roles,
        )
        return self._invoke(messages)

    def reflect(
        self,
        *,
        chapter_title: str,
        paragraph_id: str,
        paragraph_text: str,
        known_roles: list[dict[str, Any]],
        raw_output: str,
        validation: SegmentationValidationResult,
    ) -> str:
        roles_json = json.dumps(known_roles, ensure_ascii=False, indent=2)
        reflection_prompt = f"""
第一次 AI语句划分没有通过校验，请基于 reflection 修正输出。

反思重点：
- 失败类型：{validation.error_code or "unknown"}。
- 失败原因：{validation.error or "未提供"}。
- 不要解释，不要 Markdown，只返回严格 JSON。
- 必须逐字保留原段落，所有 utterances[].text 按顺序拼接后等于原段落。
- 继续按说话人/角色粒度划分；双引号对白与旁白动作之间通常需要拆开。
- 如果角色不确定，speaker_role_id 为 null 且 needs_human_review 为 true。

章节标题：{chapter_title}
paragraph_id：{paragraph_id}
已知角色：
{roles_json}

原段落：
{paragraph_text}

第一次输出：
{raw_output}
""".strip()
        return self._invoke(
            [
                {
                    "role": "system",
                    "content": "你是小说配音语句划分 reflection agent，只返回修正后的严格 JSON。",
                },
                {"role": "user", "content": reflection_prompt},
            ]
        )

    def _chat_model(self):
        provider = self.provider
        api_key_env = str(provider.get("api_key_env") or "SHUYI_TEXT_MODEL_API_KEY")
        api_key = self.api_key_lookup(api_key_env)
        if not api_key:
            raise MissingProviderCredential(f"Missing API key environment variable: {api_key_env}")

        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": str(provider.get("base_url") or ""),
            "model": str(provider.get("model") or ""),
            "temperature": 0,
            "timeout": int(provider.get("timeout_seconds", 60)),
        }
        if provider.get("max_tokens"):
            kwargs["max_tokens"] = int(provider["max_tokens"])
        if provider.get("max_retries") is not None:
            kwargs["max_retries"] = int(provider["max_retries"])
        if provider.get("extra_body"):
            kwargs["extra_body"] = dict(provider["extra_body"])
        return ChatOpenAI(**kwargs)

    def _invoke(self, messages: list[dict[str, str]]) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        converted = [
            SystemMessage(content=message["content"])
            if message.get("role") == "system"
            else HumanMessage(content=message["content"])
            for message in messages
        ]
        response = self._chat_model().invoke(converted)
        return str(response.content)


class AiSegmentationAgent:
    def __init__(
        self,
        *,
        skill: Any,
        max_reflections: int = 1,
        repair_json: Callable[[str], str] = repair_json_output_once,
    ):
        self.skill = skill
        self.max_reflections = max_reflections
        self.repair_json = repair_json

    def segment(
        self,
        *,
        chapter_title: str,
        paragraph_id: str,
        paragraph_text: str,
        known_roles: list[dict[str, Any]],
    ) -> AiSegmentationAgentResult:
        trace = ["initial segmentation requested"]
        raw_output = self.skill.segment(
            chapter_title=chapter_title,
            paragraph_id=paragraph_id,
            paragraph_text=paragraph_text,
            known_roles=known_roles,
        )
        validation = self._validate(paragraph_id, paragraph_text, raw_output, known_roles)
        if validation.ok:
            trace.append("initial segmentation accepted")
            return AiSegmentationAgentResult(raw_output, validation, 0, trace)

        trace.append(f"initial segmentation rejected: {validation.error_code}")
        reflection_count = 0
        for reflection_index in range(1, self.max_reflections + 1):
            reflection_count = reflection_index
            raw_output = self.skill.reflect(
                chapter_title=chapter_title,
                paragraph_id=paragraph_id,
                paragraph_text=paragraph_text,
                known_roles=known_roles,
                raw_output=raw_output,
                validation=validation,
            )
            validation = self._validate(paragraph_id, paragraph_text, raw_output, known_roles)
            if validation.ok:
                trace.append(f"reflection {reflection_index} accepted")
                return AiSegmentationAgentResult(raw_output, validation, reflection_count, trace)
            trace.append(f"reflection {reflection_index} rejected: {validation.error_code}")

        return AiSegmentationAgentResult(raw_output, validation, reflection_count, trace)

    def _validate(
        self,
        paragraph_id: str,
        paragraph_text: str,
        raw_output: str,
        known_roles: list[dict[str, Any]],
    ) -> SegmentationValidationResult:
        return validate_segmentation_result(
            paragraph_id=paragraph_id,
            paragraph_text=paragraph_text,
            raw_output=str(raw_output),
            known_roles=known_roles,
            repair_json=self.repair_json,
        )
