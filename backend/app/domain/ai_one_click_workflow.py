from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, TypedDict

from backend.app.domain.ai_segmentation_agent import AiSegmentationAgent, LangChainSegmentationSkill
from backend.app.domain.llm import ApiKeyLookup, MissingProviderCredential
from backend.app.domain.segmentation import SegmentationValidationResult, repair_json_output_once


@dataclass(frozen=True)
class RoleAnalysisCandidate:
    name: str | None
    aliases: list[str] = field(default_factory=list)
    gender: str | None = None
    profile: str | None = None
    voice_direction: str | None = None
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_human_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoleSelectionResult:
    role_id: str | None
    speaker_name: str
    confidence: float
    needs_human_review: bool
    reason: str


@dataclass(frozen=True)
class AiOneClickStartResult:
    status: str
    thread_id: str
    message: str
    role_candidates: list[RoleAnalysisCandidate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "thread_id": self.thread_id,
            "message": self.message,
            "role_candidates": [candidate.to_dict() for candidate in self.role_candidates],
        }


@dataclass(frozen=True)
class AiOneClickResumeResult:
    status: str
    thread_id: str
    message: str
    utterances_by_paragraph: dict[str, list[dict[str, Any]]]
    role_selection_events: list[dict[str, Any]] = field(default_factory=list)
    failure: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AiOneClickState(TypedDict, total=False):
    stage: str
    thread_id: str
    chapter_id: str
    chapter_title: str
    paragraphs: list[dict[str, Any]]
    existing_roles: list[dict[str, Any]]
    roles: list[dict[str, Any]]
    existing_utterances_by_paragraph: dict[str, list[dict[str, Any]]]
    role_candidates: list[RoleAnalysisCandidate]
    result: AiOneClickStartResult | AiOneClickResumeResult
    on_role_selected: Callable[[dict[str, Any]], None] | None


def create_whole_paragraph_utterance_drafts(paragraphs: list[Any]) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        paragraph_id = _get_text_field(paragraph, "paragraph_id", "paragraphId")
        text = _get_text_field(paragraph, "text")
        if not paragraph_id or not text:
            continue
        drafts.append(
            {
                "utterance_id": f"{paragraph_id}-u-001",
                "paragraph_id": paragraph_id,
                "speaker_name": "",
                "speaker_role_id": None,
                "voice_mode": "voice_cloning",
                "text": text,
                "emotion": "neutral",
                "speed": 1.0,
                "volume": 1.0,
                "design_prompt": None,
                "confidence": 0.0,
                "needs_human_review": True,
            }
        )
    return drafts


class LangChainRoleAnalysisSkill:
    def __init__(
        self,
        *,
        provider: dict[str, Any],
        api_key_lookup: ApiKeyLookup,
    ):
        self.provider = provider
        self.api_key_lookup = api_key_lookup

    def analyze_roles(
        self,
        *,
        chapter_id: str,
        chapter_title: str,
        chapter_text: str,
        paragraphs: list[dict[str, Any]],
        existing_roles: list[dict[str, Any]],
    ) -> list[RoleAnalysisCandidate]:
        raw = self._invoke(
            [
                {
                    "role": "system",
                    "content": "你是小说配音角色分析助手，只返回严格 JSON。",
                },
                {
                    "role": "user",
                    "content": _build_role_analysis_prompt(
                        chapter_id=chapter_id,
                        chapter_title=chapter_title,
                        chapter_text=chapter_text,
                        existing_roles=existing_roles,
                    ),
                },
            ]
        )
        return _parse_role_candidates(raw)

    def needs_segmentation(
        self,
        *,
        utterance: dict[str, Any],
        paragraph_text: str,
        roles: list[dict[str, Any]],
    ) -> bool:
        decision = self._judge_utterance(utterance=utterance, paragraph_text=paragraph_text, roles=roles)
        return bool(decision.get("segmentation_required", False))

    def choose_role(
        self,
        *,
        utterance: dict[str, Any],
        roles: list[dict[str, Any]],
        paragraph_text: str,
        chapter_title: str,
    ) -> RoleSelectionResult:
        decision = self._judge_utterance(
            utterance=utterance,
            paragraph_text=paragraph_text,
            roles=roles,
            chapter_title=chapter_title,
        )
        role_id = decision.get("role_id")
        if role_id is not None:
            role_id = str(role_id)
        return RoleSelectionResult(
            role_id=role_id,
            speaker_name=str(decision.get("speaker_name") or "未知角色"),
            confidence=_safe_float(decision.get("confidence"), default=0.0),
            needs_human_review=bool(decision.get("needs_human_review", True)),
            reason=str(decision.get("reason") or ""),
        )

    def _judge_utterance(
        self,
        *,
        utterance: dict[str, Any],
        paragraph_text: str,
        roles: list[dict[str, Any]],
        chapter_title: str = "",
    ) -> dict[str, Any]:
        raw = self._invoke(
            [
                {
                    "role": "system",
                    "content": "你是小说配音语句角色选择助手，只返回严格 JSON。",
                },
                {
                    "role": "user",
                    "content": _build_role_selection_prompt(
                        chapter_title=chapter_title,
                        paragraph_text=paragraph_text,
                        utterance=utterance,
                        roles=roles,
                    ),
                },
            ]
        )
        parsed = _parse_json_object(raw, "role selection")
        return parsed

    def _chat_model(self):
        api_key_env = str(self.provider.get("api_key_env") or "SILICONFLOW_API_KEY")
        api_key = self.api_key_lookup(api_key_env)
        if not api_key:
            raise MissingProviderCredential(f"Missing API key environment variable: {api_key_env}")

        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": str(self.provider.get("base_url") or "https://api.siliconflow.cn/v1"),
            "model": str(self.provider.get("model") or "Qwen/Qwen3-8B"),
            "temperature": 0,
            "timeout": int(self.provider.get("timeout_seconds", 60)),
        }
        if self.provider.get("max_tokens"):
            kwargs["max_tokens"] = int(self.provider["max_tokens"])
        if self.provider.get("max_retries") is not None:
            kwargs["max_retries"] = int(self.provider["max_retries"])
        if self.provider.get("extra_body"):
            kwargs["extra_body"] = dict(self.provider["extra_body"])
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


class AiSegmentationService:
    def __init__(
        self,
        *,
        provider: dict[str, Any],
        api_key_lookup: ApiKeyLookup,
    ):
        self.provider = provider
        self.api_key_lookup = api_key_lookup

    def segment_paragraph(
        self,
        *,
        chapter_title: str,
        paragraph_id: str,
        paragraph_text: str,
        known_roles: list[dict[str, Any]],
    ) -> SegmentationValidationResult:
        result = AiSegmentationAgent(
            skill=LangChainSegmentationSkill(
                provider=self.provider,
                api_key_lookup=self.api_key_lookup,
            )
        ).segment(
            chapter_title=chapter_title,
            paragraph_id=paragraph_id,
            paragraph_text=paragraph_text,
            known_roles=known_roles,
        )
        return result.validation


class AiOneClickWorkflow:
    def __init__(self, *, role_skill: Any, segmentation_service: Any):
        self.role_skill = role_skill
        self.segmentation_service = segmentation_service
        self._sessions: dict[str, AiOneClickState] = {}
        self._graph = self._build_graph()

    def start_role_analysis(
        self,
        *,
        chapter_id: str,
        chapter_title: str,
        paragraphs: list[dict[str, Any]],
        existing_roles: list[dict[str, Any]],
    ) -> AiOneClickStartResult:
        thread_id = f"ai-one-click-{uuid.uuid4().hex}"
        state: AiOneClickState = {
            "stage": "role_analysis",
            "thread_id": thread_id,
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "paragraphs": paragraphs,
            "existing_roles": existing_roles,
        }
        next_state = self._graph.invoke(state)
        self._sessions[thread_id] = dict(next_state)
        return next_state["result"]

    def resume_after_roles(
        self,
        *,
        thread_id: str,
        roles: list[dict[str, Any]],
        existing_utterances_by_paragraph: dict[str, list[dict[str, Any]]],
        on_role_selected: Callable[[dict[str, Any]], None] | None = None,
    ) -> AiOneClickResumeResult:
        if thread_id not in self._sessions:
            raise KeyError(f"Unknown ai-one-click thread_id: {thread_id}")
        state = dict(self._sessions[thread_id])
        state.update(
            {
                "stage": "resume",
                "roles": roles,
                "existing_utterances_by_paragraph": existing_utterances_by_paragraph,
                "on_role_selected": on_role_selected,
            }
        )
        next_state = self._graph.invoke(state)
        self._sessions[thread_id] = dict(next_state)
        return next_state["result"]

    def _build_graph(self):
        from langgraph.graph import END, StateGraph

        graph = StateGraph(AiOneClickState)
        graph.add_node("role_analysis", self._role_analysis_node)
        graph.add_node("sentence_role_selection", self._sentence_role_selection_node)
        graph.set_conditional_entry_point(
            lambda state: "sentence_role_selection"
            if state.get("stage") == "resume"
            else "role_analysis",
            {
                "role_analysis": "role_analysis",
                "sentence_role_selection": "sentence_role_selection",
            },
        )
        graph.add_edge("role_analysis", END)
        graph.add_edge("sentence_role_selection", END)
        return graph.compile()

    def _role_analysis_node(self, state: AiOneClickState) -> AiOneClickState:
        paragraphs = state.get("paragraphs", [])
        chapter_text = "\n\n".join(str(paragraph.get("text") or "") for paragraph in paragraphs)
        candidates = self.role_skill.analyze_roles(
            chapter_id=state["chapter_id"],
            chapter_title=state["chapter_title"],
            chapter_text=chapter_text,
            paragraphs=paragraphs,
            existing_roles=state.get("existing_roles", []),
        )
        candidates = [_candidate_from_any(candidate) for candidate in candidates]
        return {
            **state,
            "role_candidates": candidates,
            "result": AiOneClickStartResult(
                status="waiting_for_roles",
                thread_id=state["thread_id"],
                message="请先把所需角色添加到角色列表中，或绑定到已有角色。",
                role_candidates=candidates,
            ),
        }

    def _sentence_role_selection_node(self, state: AiOneClickState) -> AiOneClickState:
        roles = state.get("roles", [])
        role_ids = {str(role.get("role_id")) for role in roles if role.get("role_id")}
        utterances_by_paragraph: dict[str, list[dict[str, Any]]] = {}
        role_selection_events: list[dict[str, Any]] = []
        existing = state.get("existing_utterances_by_paragraph", {})
        paragraphs = state.get("paragraphs", [])

        for paragraph in paragraphs:
            paragraph_id = str(paragraph.get("paragraph_id") or paragraph.get("paragraphId") or "")
            paragraph_text = str(paragraph.get("text") or "")
            if not paragraph_id or not paragraph_text:
                continue
            paragraph_utterances = [
                dict(item) for item in existing.get(paragraph_id, []) if str(item.get("text") or "").strip()
            ]
            if not paragraph_utterances:
                paragraph_utterances = [
                    draft
                    for draft in create_whole_paragraph_utterance_drafts([paragraph])
                    if draft["paragraph_id"] == paragraph_id
                ]

            processed, failure, events = self._process_paragraph(
                chapter_title=state["chapter_title"],
                paragraph_id=paragraph_id,
                paragraph_text=paragraph_text,
                utterances=paragraph_utterances,
                roles=roles,
                role_ids=role_ids,
                on_role_selected=state.get("on_role_selected"),
            )
            if failure:
                result = AiOneClickResumeResult(
                    status="failed",
                    thread_id=state["thread_id"],
                    message=f"AI一键分析失败：{failure['message']}",
                    utterances_by_paragraph={},
                    role_selection_events=role_selection_events + events,
                    failure=failure,
                )
                return {**state, "result": result}
            utterances_by_paragraph[paragraph_id] = processed
            role_selection_events.extend(events)

        result = AiOneClickResumeResult(
            status="completed",
            thread_id=state["thread_id"],
            message="AI一键分析完成；请人工检查语句划分和角色后继续生成音频。",
            utterances_by_paragraph=utterances_by_paragraph,
            role_selection_events=role_selection_events,
            failure=None,
        )
        return {**state, "result": result}

    def _process_paragraph(
        self,
        *,
        chapter_title: str,
        paragraph_id: str,
        paragraph_text: str,
        utterances: list[dict[str, Any]],
        roles: list[dict[str, Any]],
        role_ids: set[str],
        on_role_selected: Callable[[dict[str, Any]], None] | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
        role_selection_events: list[dict[str, Any]] = []
        did_segment = False
        index = 0
        while index < len(utterances):
            utterance = utterances[index]
            _ensure_utterance_defaults(utterance, paragraph_id=paragraph_id, sequence=index + 1)
            if _has_role(utterance):
                index += 1
                continue
            if self.role_skill.needs_segmentation(
                utterance=utterance,
                paragraph_text=paragraph_text,
                roles=roles,
            ):
                if did_segment:
                    index += 1
                    continue
                if self.segmentation_service is None:
                    return utterances, _failure(paragraph_id, "segmentation_unavailable", "AI语句划分服务不可用"), role_selection_events
                segmentation = self.segmentation_service.segment_paragraph(
                    chapter_title=chapter_title,
                    paragraph_id=paragraph_id,
                    paragraph_text=paragraph_text,
                    known_roles=roles,
                )
                if not segmentation.ok:
                    return utterances, _failure(
                        paragraph_id,
                        segmentation.error_code or "segmentation_failed",
                        segmentation.error or "模型输出未通过 JSON/schema/文本守恒校验",
                    ), role_selection_events
                utterances = [dict(item) for item in segmentation.utterances]
                did_segment = True
                index = 0
                continue

            selection = self.role_skill.choose_role(
                utterance=utterance,
                roles=roles,
                paragraph_text=paragraph_text,
                chapter_title=chapter_title,
            )
            if selection.role_id is None and selection.needs_human_review and not did_segment:
                if self.segmentation_service is None:
                    return utterances, _failure(paragraph_id, "segmentation_unavailable", "AI语句划分服务不可用"), role_selection_events
                segmentation = self.segmentation_service.segment_paragraph(
                    chapter_title=chapter_title,
                    paragraph_id=paragraph_id,
                    paragraph_text=paragraph_text,
                    known_roles=roles,
                )
                if not segmentation.ok:
                    return utterances, _failure(
                        paragraph_id,
                        segmentation.error_code or "segmentation_failed",
                        segmentation.error or "模型输出未通过 JSON/schema/文本守恒校验",
                    ), role_selection_events
                utterances = [dict(item) for item in segmentation.utterances]
                did_segment = True
                index = 0
                continue
            if selection.role_id and selection.role_id in role_ids:
                _apply_role_selection(utterance, selection)
                event = {
                    "paragraph_id": paragraph_id,
                    "utterance_id": utterance["utterance_id"],
                    "text": utterance["text"],
                    "speaker_role_id": selection.role_id,
                    "speaker_name": selection.speaker_name,
                    "confidence": selection.confidence,
                    "needs_human_review": selection.needs_human_review,
                    "reason": selection.reason,
                }
                role_selection_events.append(event)
                if on_role_selected is not None:
                    on_role_selected(event)
            else:
                utterance["speaker_name"] = selection.speaker_name or utterance.get("speaker_name") or "未知角色"
                utterance["confidence"] = selection.confidence
                utterance["needs_human_review"] = True
            index += 1
        return utterances, None, role_selection_events


def _build_role_analysis_prompt(
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_text: str,
    existing_roles: list[dict[str, Any]],
) -> str:
    roles_json = json.dumps(existing_roles, ensure_ascii=False, indent=2)
    return f"""
请分析当前选中章节中需要配音的角色，旁白也必须作为候选之一。

要求：
- 只输出严格 JSON，不要 Markdown。
- 模型输出只是候选建议，不能视为事实；needs_human_review 默认 true。
- 如能判断，请给出角色名称、别名/称呼、性别、人设/身份/性格、推荐音色方向、证据片段和置信度。
- 证据片段必须来自原文。
- 如果角色已存在于角色列表，可仍输出候选，供用户绑定到已有角色。
- 返回结构：
{{
  "role_candidates": [
    {{
      "name": "旁白",
      "aliases": [],
      "gender": null,
      "profile": "叙述者",
      "voice_direction": "沉稳、清晰",
      "evidence": ["原文片段"],
      "confidence": 0.8,
      "needs_human_review": true
    }}
  ]
}}

chapter_id：{chapter_id}
章节标题：{chapter_title}
现有角色列表：
{roles_json}

章节正文：
{chapter_text}
""".strip()


def _build_role_selection_prompt(
    *,
    chapter_title: str,
    paragraph_text: str,
    utterance: dict[str, Any],
    roles: list[dict[str, Any]],
) -> str:
    roles_json = json.dumps(roles, ensure_ascii=False, indent=2)
    utterance_json = json.dumps(utterance, ensure_ascii=False, indent=2)
    return f"""
请判断当前语句是否可以由单一角色配音，并在可以时选择最合适的已知角色。

要求：
- 只输出严格 JSON，不要 Markdown。
- 如果语句包含多人对白、对白 + 旁白动作 + 对白，或角色归属不确定，segmentation_required=true。
- role_id 只能使用已知角色 role_id；无法判断时为 null，needs_human_review=true。
- 不要改写 utterance.text。
- 返回结构：
{{
  "segmentation_required": false,
  "role_id": "narrator",
  "speaker_name": "旁白",
  "confidence": 0.8,
  "needs_human_review": true,
  "reason": "简短理由"
}}

章节标题：{chapter_title}
原段落：
{paragraph_text}
语句：
{utterance_json}
已知角色：
{roles_json}
""".strip()


def _parse_role_candidates(raw_output: str) -> list[RoleAnalysisCandidate]:
    parsed = _parse_json_object(raw_output, "role analysis")
    candidates = parsed.get("role_candidates")
    if not isinstance(candidates, list):
        raise TypeError("role analysis output must include role_candidates list")
    return [_candidate_from_any(candidate) for candidate in candidates]


def _parse_json_object(raw_output: str, label: str) -> dict[str, Any]:
    candidate = repair_json_output_once(str(raw_output))
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} output is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise TypeError(f"{label} output must be a JSON object")
    return parsed


def _candidate_from_any(candidate: Any) -> RoleAnalysisCandidate:
    if isinstance(candidate, RoleAnalysisCandidate):
        return candidate
    if not isinstance(candidate, dict):
        raise TypeError("role candidate must be an object")
    return RoleAnalysisCandidate(
        name=str(candidate["name"]) if candidate.get("name") is not None else None,
        aliases=[str(alias) for alias in candidate.get("aliases") or []],
        gender=str(candidate["gender"]) if candidate.get("gender") is not None else None,
        profile=str(candidate["profile"]) if candidate.get("profile") is not None else None,
        voice_direction=str(candidate["voice_direction"]) if candidate.get("voice_direction") is not None else None,
        evidence=[str(item) for item in candidate.get("evidence") or []],
        confidence=max(0.0, min(1.0, _safe_float(candidate.get("confidence"), default=0.0))),
        needs_human_review=bool(candidate.get("needs_human_review", True)),
    )


def _get_text_field(source: Any, *names: str) -> str:
    for name in names:
        if isinstance(source, dict) and name in source:
            return str(source.get(name) or "")
        if hasattr(source, name):
            return str(getattr(source, name) or "")
    return ""


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ensure_utterance_defaults(utterance: dict[str, Any], *, paragraph_id: str, sequence: int) -> None:
    utterance.setdefault("utterance_id", f"{paragraph_id}-u-{sequence:03d}")
    utterance.setdefault("paragraph_id", paragraph_id)
    utterance.setdefault("speaker_name", "")
    utterance.setdefault("speaker_role_id", utterance.get("role_id") or None)
    utterance.setdefault("voice_mode", "voice_cloning")
    utterance.setdefault("emotion", "neutral")
    utterance.setdefault("speed", 1.0)
    utterance.setdefault("volume", 1.0)
    utterance.setdefault("design_prompt", None)
    utterance.setdefault("confidence", 0.0)
    utterance.setdefault("needs_human_review", True)


def _has_role(utterance: dict[str, Any]) -> bool:
    return bool(utterance.get("speaker_role_id") or utterance.get("role_id"))


def _apply_role_selection(utterance: dict[str, Any], selection: RoleSelectionResult) -> None:
    utterance["speaker_role_id"] = selection.role_id
    utterance["speaker_name"] = selection.speaker_name
    utterance["confidence"] = selection.confidence
    utterance["needs_human_review"] = selection.needs_human_review


def _failure(paragraph_id: str, error_code: str, message: str) -> dict[str, Any]:
    return {
        "paragraph_id": paragraph_id,
        "error_code": error_code,
        "message": f"{error_code}: {message}",
    }
