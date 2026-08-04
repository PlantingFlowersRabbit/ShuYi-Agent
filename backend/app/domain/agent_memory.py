from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

MEMORY_CONFIDENCE_LEVELS = {
    "model_suggested",
    "user_confirmed",
    "system_verified",
    "rejected",
}
TRUSTED_MEMORY_CONFIDENCE = {"user_confirmed", "system_verified"}


def build_long_term_memory_fact(*, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    subject = _required_text(payload, "subject")
    predicate = _required_text(payload, "predicate")
    obj = _required_text(payload, "object")
    writer = str(payload.get("writer") or payload.get("created_by") or "user").strip().lower()
    source_type = str(payload.get("source_type") or "manual").strip() or "manual"
    confidence = coerce_memory_confidence(
        payload.get("confidence"),
        writer=writer,
        source_type=source_type,
    )
    source_id = str(payload.get("source_id") or f"{source_type}:{subject}:{predicate}:{obj}").strip()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    now = datetime.now(UTC).isoformat()
    return {
        "fact_id": _stable_id(project_id, subject, predicate, obj, source_id),
        "project_id": project_id,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "confidence": confidence,
        "source_id": source_id,
        "source_type": source_type,
        "writer": writer,
        "metadata": metadata,
        "notes": str(payload.get("notes") or ""),
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
    }


def coerce_memory_confidence(value: Any, *, writer: str, source_type: str) -> str:
    requested = str(value or "").strip()
    if requested == "rejected":
        return "rejected"
    if writer in {"user", "human"} or source_type == "user_correction":
        return requested if requested in MEMORY_CONFIDENCE_LEVELS else "user_confirmed"
    if writer == "system":
        return requested if requested in {"system_verified", "rejected"} else "system_verified"
    if requested in TRUSTED_MEMORY_CONFIDENCE:
        return "model_suggested"
    return requested if requested in MEMORY_CONFIDENCE_LEVELS else "model_suggested"


def build_story_memory_context(
    *,
    facts: list[dict[str, Any]],
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    matched = [fact for fact in facts if _matches_query(fact, query)]
    ordered = sorted(matched, key=_fact_priority)
    facts_for_prompt = [fact for fact in ordered if fact.get("confidence") in TRUSTED_MEMORY_CONFIDENCE]
    candidate_facts = [fact for fact in ordered if fact.get("confidence") == "model_suggested"]
    rejected_facts = [fact for fact in ordered if fact.get("confidence") == "rejected"]
    safe_limit = max(1, min(int(limit or 20), 100))
    return {
        "facts_for_prompt": facts_for_prompt[:safe_limit],
        "candidate_facts": candidate_facts[:safe_limit],
        "rejected_facts": rejected_facts[:safe_limit],
        "policy": {
            "trusted": ["user_confirmed", "system_verified"],
            "candidate_only": ["model_suggested"],
            "excluded_from_prompt": ["rejected"],
        },
    }


def build_run_memory_snapshot(
    *,
    project_id: str,
    run_id: str,
    payload: dict[str, Any],
    tool_results: list[dict[str, Any]] | None = None,
    final_status: str = "completed",
) -> dict[str, Any]:
    tool_results = tool_results or []
    errors = [item for item in tool_results if item.get("status") == "failed"]
    errors.extend(item for item in payload.get("errors") or [] if isinstance(item, dict))
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    if not steps:
        steps = [
            {
                "step_id": item.get("tool_call_id") or f"step-{index:04d}",
                "tool_name": item.get("tool_name") or "",
                "status": item.get("status") or "unknown",
                "duration_ms": item.get("duration_ms") or 0,
            }
            for index, item in enumerate(tool_results, start=1)
        ]
    now = datetime.now(UTC).isoformat()
    return {
        "run_id": run_id,
        "project_id": project_id,
        "current_goal": str(payload.get("current_goal") or ""),
        "current_plan": [str(item) for item in payload.get("current_plan") or []],
        "steps": steps,
        "tool_calls": tool_results,
        "intermediate_results": payload.get("intermediate_results") or [],
        "errors": errors,
        "reflection": payload.get("reflection") or payload.get("reflection_trace") or [],
        "final_output": payload.get("final_output")
        if isinstance(payload.get("final_output"), dict)
        else {
            "status": final_status,
            "succeeded_count": sum(1 for item in tool_results if item.get("status") == "succeeded"),
            "failed_count": sum(1 for item in tool_results if item.get("status") == "failed"),
        },
        "status": "needs_review" if errors else final_status,
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
    }


def _fact_priority(fact: dict[str, Any]) -> tuple[int, str, str]:
    priority = {
        "user_confirmed": 0,
        "system_verified": 1,
        "model_suggested": 2,
        "rejected": 3,
    }.get(str(fact.get("confidence") or ""), 4)
    return priority, str(fact.get("subject") or ""), str(fact.get("predicate") or "")


def _matches_query(fact: dict[str, Any], query: str) -> bool:
    cleaned = query.strip()
    if not cleaned:
        return True
    haystack = " ".join(
        str(fact.get(key) or "") for key in ("subject", "predicate", "object", "notes")
    )
    return cleaned in haystack


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} 不能为空")
    return value


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()[:24]
