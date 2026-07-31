from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, TypedDict

from backend.app.domain.ai_segmentation_agent import AiSegmentationAgent, LangChainSegmentationSkill
from backend.app.domain.llm import ApiKeyLookup, MissingProviderCredential
from backend.app.domain.roles import RoleCard, RoleCollection
from backend.app.domain.segmentation import SegmentationValidationResult, repair_json_output_once
from backend.app.domain.voices import (
    VoiceResource,
    VoiceResourceCollection,
    generated_voice_content,
)


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
class BatchRoleSelectionReport:
    status: str
    total_count: int
    skipped_count: int
    success_count: int
    split_count: int
    uncertain_count: int
    failed_count: int
    errors: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AutoRoleCreationReport:
    added_count: int
    updated_count: int
    matched_existing_count: int
    generated_voice_count: int
    actions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AiOneClickStartResult:
    status: str
    thread_id: str
    message: str
    role_candidates: list[RoleAnalysisCandidate]
    auto_role_report: AutoRoleCreationReport | None = None
    roles: list[dict[str, Any]] = field(default_factory=list)
    voices: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "thread_id": self.thread_id,
            "message": self.message,
            "role_candidates": [candidate.to_dict() for candidate in self.role_candidates],
            "auto_role_report": self.auto_role_report.to_dict() if self.auto_role_report else None,
            "roles": self.roles,
            "voices": self.voices,
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

    def choose_roles_batch(
        self,
        *,
        chapter_id: str,
        chapter_title: str,
        statements: list[dict[str, Any]],
        roles: list[dict[str, Any]],
        paragraphs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raw = self._invoke(
            [
                {
                    "role": "system",
                    "content": "你是小说配音批量语句角色选择助手，只返回严格 JSON。",
                },
                {
                    "role": "user",
                    "content": _build_batch_role_selection_prompt(
                        chapter_id=chapter_id,
                        chapter_title=chapter_title,
                        statements=statements,
                        roles=roles,
                        paragraphs=paragraphs,
                    ),
                },
            ]
        )
        return _parse_batch_role_selection(raw)

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


class BatchRoleSelectionService:
    def __init__(self, role_skill: Any, *, segmentation_service: Any | None = None, batch_size: int = 60):
        self.role_skill = role_skill
        self.segmentation_service = segmentation_service
        self.batch_size = max(1, batch_size)

    def select_roles_for_statements_batch(
        self,
        *,
        chapter_id: str,
        chapter_title: str,
        paragraphs: list[dict[str, Any]],
        utterances_by_paragraph: dict[str, list[dict[str, Any]]],
        roles: list[dict[str, Any]],
        on_role_selected: Callable[[dict[str, Any]], None] | None = None,
    ) -> BatchRoleSelectionReport:
        skipped_count = 0
        success_count = 0
        split_count = 0
        uncertain_count = 0
        failed_count = 0
        errors: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        split_paragraphs: set[str] = set()
        paragraph_by_id = {
            str(paragraph.get("paragraph_id") or paragraph.get("paragraphId") or ""): paragraph
            for paragraph in paragraphs
        }
        role_by_id = {str(role.get("role_id")): role for role in roles if role.get("role_id")}

        for paragraph_id, utterances in utterances_by_paragraph.items():
            for index, utterance in enumerate(utterances, start=1):
                _ensure_utterance_defaults(utterance, paragraph_id=paragraph_id, sequence=index)
                if _has_role(utterance):
                    skipped_count += 1

        while True:
            pending = _pending_role_statements(utterances_by_paragraph, paragraph_by_id)
            if not pending:
                break
            chunk = pending[: self.batch_size]
            try:
                parsed = self._choose_batch(
                    chapter_id=chapter_id,
                    chapter_title=chapter_title,
                    statements=chunk,
                    roles=roles,
                    paragraphs=paragraphs,
                    paragraph_by_id=paragraph_by_id,
                )
            except (TypeError, ValueError, KeyError, RuntimeError) as exc:
                failed_count += len(chunk)
                errors.append(
                    {
                        "paragraph_id": str(chunk[0].get("paragraph_id") or ""),
                        "error_code": "invalid_batch_json",
                        "message": f"批量角色选择 JSON 解析失败：{exc}",
                    }
                )
                return BatchRoleSelectionReport(
                    "failed",
                    skipped_count + success_count + failed_count + uncertain_count,
                    skipped_count,
                    success_count,
                    split_count,
                    uncertain_count,
                    failed_count,
                    errors,
                    events,
                )

            decisions = _batch_decisions_by_statement_id(parsed)
            progressed = False
            for statement in chunk:
                utterance = statement["_utterance"]
                statement_id = statement["statement_id"]
                if _has_role(utterance):
                    continue
                decision = decisions.get(statement_id)
                if decision is None:
                    utterance["needs_human_review"] = True
                    uncertain_count += 1
                    progressed = True
                    continue
                action = str(decision.get("action") or "uncertain")
                role_id = str(decision.get("role_id") or "") if decision.get("role_id") else None
                if action == "select_role" and role_id in role_by_id and not _has_role(utterance):
                    role = role_by_id[role_id]
                    selection = RoleSelectionResult(
                        role_id=role_id,
                        speaker_name=str(role.get("name") or decision.get("speaker_name") or role_id),
                        confidence=_safe_float(decision.get("confidence"), default=0.0),
                        needs_human_review=False,
                        reason=str(decision.get("reason") or ""),
                    )
                    _apply_role_selection(utterance, selection)
                    event = {
                        "paragraph_id": statement["paragraph_id"],
                        "utterance_id": statement_id,
                        "text": utterance["text"],
                        "speaker_role_id": role_id,
                        "speaker_name": selection.speaker_name,
                        "confidence": selection.confidence,
                        "needs_human_review": selection.needs_human_review,
                        "reason": selection.reason,
                    }
                    events.append(event)
                    if on_role_selected is not None:
                        on_role_selected(event)
                    success_count += 1
                    progressed = True
                    continue
                if action == "needs_split":
                    paragraph_id = str(statement["paragraph_id"])
                    if paragraph_id not in split_paragraphs:
                        split_paragraphs.add(paragraph_id)
                        split_count += 1
                        failure = self._split_paragraph(
                            chapter_title=chapter_title,
                            paragraph_id=paragraph_id,
                            paragraph_by_id=paragraph_by_id,
                            utterances_by_paragraph=utterances_by_paragraph,
                            roles=roles,
                        )
                        if failure:
                            failed_count += 1
                            errors.append(failure)
                            return BatchRoleSelectionReport(
                                "failed",
                                skipped_count + success_count + failed_count + uncertain_count,
                                skipped_count,
                                success_count,
                                split_count,
                                uncertain_count,
                                failed_count,
                                errors,
                                events,
                            )
                    progressed = True
                    break
                utterance["speaker_name"] = utterance.get("speaker_name") or "未知角色"
                utterance["confidence"] = _safe_float(decision.get("confidence"), default=0.0)
                utterance["needs_human_review"] = True
                uncertain_count += 1
                progressed = True
            if not progressed:
                break

        return BatchRoleSelectionReport(
            "completed",
            skipped_count + success_count + failed_count + uncertain_count,
            skipped_count,
            success_count,
            split_count,
            uncertain_count,
            failed_count,
            errors,
            events,
        )

    def _choose_batch(
        self,
        *,
        chapter_id: str,
        chapter_title: str,
        statements: list[dict[str, Any]],
        roles: list[dict[str, Any]],
        paragraphs: list[dict[str, Any]],
        paragraph_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        model_statements = [{key: value for key, value in item.items() if key != "_utterance"} for item in statements]
        if hasattr(self.role_skill, "choose_roles_batch"):
            raw = self.role_skill.choose_roles_batch(
                chapter_id=chapter_id,
                chapter_title=chapter_title,
                statements=model_statements,
                roles=roles,
                paragraphs=paragraphs,
            )
            return _parse_batch_role_selection(raw)
        return {
            "items": [
                self._legacy_decision(
                    statement=statement,
                    chapter_title=chapter_title,
                    roles=roles,
                    paragraph_by_id=paragraph_by_id,
                )
                for statement in statements
            ]
        }

    def _legacy_decision(
        self,
        *,
        statement: dict[str, Any],
        chapter_title: str,
        roles: list[dict[str, Any]],
        paragraph_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        utterance = statement["_utterance"]
        paragraph_text = str(paragraph_by_id.get(statement["paragraph_id"], {}).get("text") or "")
        if hasattr(self.role_skill, "needs_segmentation") and self.role_skill.needs_segmentation(
            utterance=utterance,
            paragraph_text=paragraph_text,
            roles=roles,
        ):
            return {
                "statement_id": statement["statement_id"],
                "action": "needs_split",
                "role_id": None,
                "confidence": 0.0,
                "reason": "legacy needs_segmentation returned true",
                "evidence": "",
            }
        selection = self.role_skill.choose_role(
            utterance=utterance,
            roles=roles,
            paragraph_text=paragraph_text,
            chapter_title=chapter_title,
        )
        action = "select_role" if selection.role_id else "needs_split" if selection.needs_human_review else "uncertain"
        return {
            "statement_id": statement["statement_id"],
            "action": action,
            "role_id": selection.role_id,
            "confidence": selection.confidence,
            "reason": selection.reason,
            "evidence": utterance.get("text", ""),
        }

    def _split_paragraph(
        self,
        *,
        chapter_title: str,
        paragraph_id: str,
        paragraph_by_id: dict[str, dict[str, Any]],
        utterances_by_paragraph: dict[str, list[dict[str, Any]]],
        roles: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if self.segmentation_service is None:
            return _failure(paragraph_id, "segmentation_unavailable", "AI语句划分服务不可用")
        paragraph = paragraph_by_id.get(paragraph_id, {})
        segmentation = self.segmentation_service.segment_paragraph(
            chapter_title=chapter_title,
            paragraph_id=paragraph_id,
            paragraph_text=str(paragraph.get("text") or ""),
            known_roles=roles,
        )
        if not segmentation.ok:
            return _failure(
                paragraph_id,
                segmentation.error_code or "segmentation_failed",
                segmentation.error or "模型输出未通过 JSON/schema/文本守恒校验",
            )
        utterances_by_paragraph[paragraph_id] = [dict(item) for item in segmentation.utterances]
        for index, utterance in enumerate(utterances_by_paragraph[paragraph_id], start=1):
            _ensure_utterance_defaults(utterance, paragraph_id=paragraph_id, sequence=index)
        return None


class AiOneClickWorkflow:
    def __init__(
        self,
        *,
        role_skill: Any,
        segmentation_service: Any,
        role_collection: RoleCollection | None = None,
        voice_collection: VoiceResourceCollection | None = None,
        voice_generator: Callable[[RoleAnalysisCandidate], VoiceResource | dict[str, Any]] | None = None,
    ):
        self.role_skill = role_skill
        self.segmentation_service = segmentation_service
        self.role_collection = role_collection
        self.voice_collection = voice_collection
        self.voice_generator = voice_generator
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
        auto_report: AutoRoleCreationReport | None = None
        roles: list[dict[str, Any]] = []
        voices: list[dict[str, Any]] = []
        message = "请先把所需角色添加到角色列表中，或绑定到已有角色。"
        if self.role_collection is not None and self.voice_collection is not None:
            auto_report = auto_apply_role_candidates(
                candidates=candidates,
                roles=self.role_collection,
                voices=self.voice_collection,
                generate_voice=self.voice_generator,
            )
            roles = [role.to_dict() for role in self.role_collection.list()]
            voices = [voice.to_dict() for voice in self.voice_collection.list()]
            message = "AI已自动添加/更新角色并匹配音色；请确认角色列表后继续。"
        return {
            **state,
            "role_candidates": candidates,
            "result": AiOneClickStartResult(
                status="waiting_for_roles",
                thread_id=state["thread_id"],
                message=message,
                role_candidates=candidates,
                auto_role_report=auto_report,
                roles=roles,
                voices=voices,
            ),
        }

    def _sentence_role_selection_node(self, state: AiOneClickState) -> AiOneClickState:
        roles = state.get("roles", [])
        utterances_by_paragraph: dict[str, list[dict[str, Any]]] = {}
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
            utterances_by_paragraph[paragraph_id] = paragraph_utterances

        batch_report = BatchRoleSelectionService(
            self.role_skill,
            segmentation_service=self.segmentation_service,
        ).select_roles_for_statements_batch(
            chapter_id=state["chapter_id"],
            chapter_title=state["chapter_title"],
            paragraphs=paragraphs,
            utterances_by_paragraph=utterances_by_paragraph,
            roles=roles,
            on_role_selected=state.get("on_role_selected"),
        )
        if batch_report.status == "failed":
            failure = batch_report.errors[0] if batch_report.errors else {
                "paragraph_id": "",
                "error_code": "batch_role_selection_failed",
                "message": "批量角色选择失败",
            }
            result = AiOneClickResumeResult(
                status="failed",
                thread_id=state["thread_id"],
                message=f"AI一键分析失败：{failure['message']}",
                utterances_by_paragraph={},
                role_selection_events=batch_report.events,
                failure=failure,
            )
            return {**state, "result": result}

        result = AiOneClickResumeResult(
            status="completed",
            thread_id=state["thread_id"],
            message="AI一键分析完成；请人工检查语句划分和角色，或点击“一键生成配音”。",
            utterances_by_paragraph=utterances_by_paragraph,
            role_selection_events=batch_report.events,
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


def auto_apply_role_candidates(
    *,
    candidates: list[RoleAnalysisCandidate | dict[str, Any]],
    roles: RoleCollection,
    voices: VoiceResourceCollection,
    generate_voice: Callable[[RoleAnalysisCandidate], VoiceResource | dict[str, Any]] | None = None,
    voice_match_threshold: float = 0.55,
) -> AutoRoleCreationReport:
    actions: list[dict[str, Any]] = []
    added_count = 0
    updated_count = 0
    matched_existing_count = 0
    generated_voice_count = 0

    for raw_candidate in candidates:
        candidate = _candidate_from_any(raw_candidate)
        if not candidate.name:
            continue
        existing = _find_matching_role(candidate, roles)
        if existing is not None:
            matched_existing_count += 1
            role = existing
            action = "matched_existing"
        else:
            role = RoleCard(
                role_id=_stable_role_id(candidate.name, roles),
                name=candidate.name,
                description=candidate.profile or candidate.voice_direction or "AI自动识别角色",
                voice_mode="voice_cloning",
                reference_audio_path=None,
                reference_text=None,
                design_prompt=None,
                voice_resource_id=None,
                aliases=candidate.aliases,
                gender=candidate.gender,
                profile=candidate.profile,
            )
            added_count += 1
            action = "added"

        voice, score, reason = _best_voice_match(candidate, voices.list())
        generated_by_ai = False
        if (voice is None or score < voice_match_threshold) and action == "matched_existing" and role.voice_resource_id:
            voice = VoiceResource(
                voice_id=role.voice_resource_id,
                name=role.name,
                description=role.voice_description or role.description,
                reference_text=role.reference_text or generated_voice_content(role.name, role.description),
                reference_audio_path=role.reference_audio_path or "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
                generated=role.voice_generated_by_ai,
                gender=role.gender,
                suitable_role_types=[item for item in [role.profile, role.description] if item],
                playable_audio_path=role.playable_voice_path or role.reference_audio_path,
            )
            score = role.voice_match_score if role.voice_match_score is not None else 1.0
            reason = role.voice_match_reason or "复用已有角色绑定音色。"
        elif voice is None or score < voice_match_threshold:
            voice = _generate_voice_for_candidate(candidate, voices, generate_voice)
            generated_voice_count += 1
            generated_by_ai = True
            score = 1.0
            reason = "音色资源库没有达到阈值的匹配项，已生成新音色资源。"

        updated = role.with_updates(
            description=candidate.profile or role.description,
            aliases=_merge_aliases(role.aliases, candidate.aliases),
            gender=candidate.gender or role.gender,
            profile=candidate.profile or role.profile,
            voice_resource_id=voice.voice_id,
            reference_audio_path=voice.reference_audio_path,
            reference_text=voice.reference_text,
            design_prompt=None,
            voice_mode="voice_cloning",
            voice_description=voice.description,
            voice_sample_text=voice.reference_text,
            playable_voice_path=voice.playable_audio_path or voice.reference_audio_path,
            voice_match_score=score,
            voice_match_reason=reason,
            voice_generated_by_ai=generated_by_ai,
        )
        roles.upsert(updated)
        if action == "matched_existing":
            updated_count += 1
        actions.append(
            {
                "action": action,
                "role_id": updated.role_id,
                "role_name": updated.name,
                "voice_resource_id": voice.voice_id,
                "voice_match_score": score,
                "voice_match_reason": reason,
                "voice_generated_by_ai": generated_by_ai,
            }
        )

    return AutoRoleCreationReport(
        added_count=added_count,
        updated_count=updated_count,
        matched_existing_count=matched_existing_count,
        generated_voice_count=generated_voice_count,
        actions=actions,
    )


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


def _build_batch_role_selection_prompt(
    *,
    chapter_id: str,
    chapter_title: str,
    statements: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    paragraphs: list[dict[str, Any]],
) -> str:
    roles_json = json.dumps(roles, ensure_ascii=False, indent=2)
    statements_json = json.dumps(statements, ensure_ascii=False, indent=2)
    paragraphs_json = json.dumps(paragraphs, ensure_ascii=False, indent=2)
    return f"""
请批量判断当前章节多条语句的配音角色。

硬性要求：
- 只输出严格 JSON，不要 Markdown。
- 只能从已知角色 role_id 中选择；旁白也必须是一个已有角色。
- 只处理传入 statements 中的 statement_id，不要新增、删除或改写 text。
- 如果某条语句不是单人配音文本，包含多人对白、对白 + 旁白动作 + 对白，返回 action=\"needs_split\"。
- 如果角色归属不确定，返回 action=\"uncertain\"，role_id=null，不要乱选。
- 已有 role_id 的语句不会传给你；不要推测未提供语句。

返回结构：
{{
  "items": [
    {{
      "statement_id": "p-0001-u-001",
      "action": "select_role | needs_split | uncertain | skip",
      "role_id": "narrator 或 null",
      "confidence": 0.0,
      "reason": "简短原因",
      "evidence": "文本片段"
    }}
  ]
}}

chapter_id：{chapter_id}
章节标题：{chapter_title}
已知角色：
{roles_json}
当前段落上下文：
{paragraphs_json}
待判断语句：
{statements_json}
""".strip()


def _parse_role_candidates(raw_output: str) -> list[RoleAnalysisCandidate]:
    parsed = _parse_json_object(raw_output, "role analysis")
    candidates = parsed.get("role_candidates")
    if not isinstance(candidates, list):
        raise TypeError("role analysis output must include role_candidates list")
    return [_candidate_from_any(candidate) for candidate in candidates]


def _parse_batch_role_selection(raw_output: Any) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        parsed = raw_output
    else:
        parsed = _parse_json_object(str(raw_output), "batch role selection")
    items = parsed.get("items")
    if not isinstance(items, list):
        raise TypeError("batch role selection output must include items list")
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("batch role selection items must be objects")
        if not item.get("statement_id"):
            raise TypeError("batch role selection item missing statement_id")
    return parsed


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


def _find_matching_role(candidate: RoleAnalysisCandidate, roles: RoleCollection) -> RoleCard | None:
    candidate_name = _normalize_name(candidate.name)
    candidate_aliases = {_normalize_name(alias) for alias in candidate.aliases}
    for role in roles.list():
        role_names = {_normalize_name(role.name), *{_normalize_name(alias) for alias in role.aliases}}
        if candidate_name and candidate_name in role_names:
            return role
        if candidate_aliases.intersection(role_names):
            return role
        if candidate_name == _normalize_name("旁白") and _normalize_name(role.name) == _normalize_name("旁白"):
            return role
    return None


def _best_voice_match(
    candidate: RoleAnalysisCandidate,
    voices: list[VoiceResource],
) -> tuple[VoiceResource | None, float, str]:
    best_voice: VoiceResource | None = None
    best_score = 0.0
    best_reason = ""
    candidate_terms = _terms(
        " ".join(
            [
                candidate.gender or "",
                candidate.profile or "",
                candidate.voice_direction or "",
                candidate.name or "",
            ]
        )
    )
    for voice in voices:
        voice_terms = _terms(
            " ".join(
                [
                    voice.name,
                    voice.gender or "",
                    voice.description,
                    " ".join(voice.suitable_role_types),
                ]
            )
        )
        score = 0.0
        reasons: list[str] = []
        if candidate.gender and voice.gender and candidate.gender == voice.gender:
            score += 0.35
            reasons.append("性别匹配")
        overlap = candidate_terms.intersection(voice_terms)
        if overlap:
            score += min(0.55, len(overlap) * 0.12)
            reasons.append(f"关键词匹配：{'、'.join(sorted(overlap)[:4])}")
        if candidate.voice_direction and candidate.voice_direction in voice.description:
            score += 0.25
            reasons.append("推荐音色方向命中描述")
        if score > best_score:
            best_score = min(score, 1.0)
            best_voice = voice
            best_reason = "；".join(reasons) or "音色描述接近"
    return best_voice, best_score, best_reason


def _generate_voice_for_candidate(
    candidate: RoleAnalysisCandidate,
    voices: VoiceResourceCollection,
    generate_voice: Callable[[RoleAnalysisCandidate], VoiceResource | dict[str, Any]] | None,
) -> VoiceResource:
    if generate_voice is not None:
        resource = generate_voice(candidate)
    else:
        voice_id = f"voice-auto-{_role_slug(candidate.name or '角色')}"
        resource = VoiceResource(
            voice_id=voice_id,
            name=f"{candidate.name or '角色'}专属音色",
            gender=candidate.gender,
            description=candidate.voice_direction or candidate.profile or "AI自动生成音色",
            suitable_role_types=[item for item in [candidate.gender, candidate.profile] if item],
            reference_text=generated_voice_content(
                f"{candidate.name or '角色'}专属音色",
                candidate.voice_direction or candidate.profile or "自然、清晰、稳定",
            ),
            reference_audio_path="assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
            generated=True,
        )
    voice = voices.upsert(resource)
    return voice


def _merge_aliases(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    for alias in [*existing, *incoming]:
        if alias and alias not in merged:
            merged.append(alias)
    return merged


def _pending_role_statements(
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    paragraph_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for paragraph_id, utterances in utterances_by_paragraph.items():
        paragraph = paragraph_by_id.get(paragraph_id, {})
        for order, utterance in enumerate(utterances, start=1):
            if _has_role(utterance) or not str(utterance.get("text") or "").strip():
                continue
            statements.append(
                {
                    "statement_id": str(utterance.get("utterance_id") or utterance.get("statement_id")),
                    "paragraph_id": paragraph_id,
                    "paragraph_order": _first_number(paragraph_id),
                    "statement_order": order,
                    "text": str(utterance.get("text") or ""),
                    "context": str(paragraph.get("text") or ""),
                    "_utterance": utterance,
                }
            )
    return statements


def _batch_decisions_by_statement_id(parsed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["statement_id"]): item for item in parsed.get("items", [])}


def _stable_role_id(name: str, roles: RoleCollection) -> str:
    base = f"role-{_role_slug(name)}"
    role_ids = {role.role_id for role in roles.list()}
    if base not in role_ids:
        return base
    index = 2
    while f"{base}-{index}" in role_ids:
        index += 1
    return f"{base}-{index}"


def _role_slug(name: str) -> str:
    transliteration = {
        "林": "lin",
        "清": "qing",
        "佩": "pei",
        "罗": "luo",
        "旁": "pang",
        "白": "bai",
    }
    converted = "".join(transliteration.get(char, char) for char in name)
    slug = re.sub(r"[^a-z0-9]+", "-", converted.lower()).strip("-")
    if slug:
        return slug
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name)).split("-", maxsplit=1)[0]


def _normalize_name(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _terms(value: str) -> set[str]:
    tokens = {token for token in re.split(r"[\s,，、。；;：:（）()【】\[\]-]+", value) if token}
    for marker in ["男", "女", "旁白", "冷静", "清亮", "沉稳", "年轻", "成熟", "主角", "佣兵"]:
        if marker in value:
            tokens.add(marker)
    return tokens


def _first_number(value: str) -> int:
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else 1
