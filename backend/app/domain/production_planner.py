from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from backend.app.domain.tool_registry import (
    ToolExecutionContext,
    ToolRegistry,
    execute_tool_plan,
)

PLANNER_AGENT_ID = "production_planner"
PLANNER_STEP_IDS = (
    "check_project_status",
    "find_unsegmented_paragraphs",
    "segment_dialogue",
    "search_story_bible",
    "assign_roles",
    "detect_long_utterances",
    "split_long_text",
    "check_tts_health",
    "generate_dubbing",
    "retry_failed_dubbing",
    "pre_export_quality_check",
    "review_remaining_issues",
)


def build_production_planner_run(
    *,
    project_id: str,
    payload: dict[str, Any],
    registered_tools: set[str],
) -> dict[str, Any]:
    goal = str(payload.get("goal") or payload.get("current_goal") or "").strip()
    if not goal:
        raise ValueError("Planner goal 不能为空")
    run_id = str(payload.get("run_id") or f"planner-{secrets.token_hex(8)}")
    chapter_id = str(payload.get("chapter_id") or "")
    quality_args = _quality_arguments(payload)
    query_text = str(payload.get("query") or goal)
    long_text = _first_long_text(payload, max_chars=int(quality_args["max_utterance_chars"]))
    steps = [
        _tool_step(
            step_id="check_project_status",
            title="检查章节状态",
            tool_name="get_project_status",
            arguments=quality_args,
        ),
        _tool_step(
            step_id="assign_roles",
            title="找出未选角色台词",
            tool_name="query_utterances",
            arguments={**quality_args, "status": "unselected_role"},
        ),
        _tool_step(
            step_id="find_unsegmented_paragraphs",
            title="找出未划分段落",
            tool_name="get_project_status",
            arguments=quality_args,
        ),
        _manual_step(
            step_id="segment_dialogue",
            title="跑台词划分",
            rationale="台词划分仍由现有章节/配音编排 Agent 入口执行，Planner 负责暂停并提示人工或上游 Agent 继续。",
        ),
        _tool_step(
            step_id="search_story_bible",
            title="检索 Story Bible",
            tool_name="search_story_memory",
            arguments={"query": query_text, "top_k": 5},
        ),
        _tool_step(
            step_id="detect_long_utterances",
            title="检测超长台词",
            tool_name="query_utterances",
            arguments={**quality_args, "status": "long_utterance"},
        ),
        _tool_step(
            step_id="split_long_text",
            title="拆分并校验文本守恒",
            tool_name="suggest_long_text_split",
            arguments={"text": long_text, "max_chars": quality_args["max_utterance_chars"]},
        ),
        _tool_step(
            step_id="check_tts_health",
            title="查询 TTS 状态",
            tool_name="check_tts_health",
            arguments={},
        ),
        _manual_step(
            step_id="generate_dubbing",
            title="生成配音",
            rationale="真实音频生成仍走受控配音接口；Planner 在检查通过后给出下一步执行状态。",
        ),
        _tool_step(
            step_id="retry_failed_dubbing",
            title="重试失败",
            tool_name="query_utterances",
            arguments={**quality_args, "status": "dubbing_failed"},
        ),
        _tool_step(
            step_id="pre_export_quality_check",
            title="运行导出前质量检查",
            tool_name="get_project_status",
            arguments=quality_args,
        ),
        _manual_step(
            step_id="review_remaining_issues",
            title="复盘剩余问题",
            rationale="Reviewer 汇总失败步骤、质量阻塞项和人工介入点。",
        ),
    ]
    _validate_planner_steps(steps, registered_tools=registered_tools)
    now = _now()
    return {
        "run_id": run_id,
        "project_id": project_id,
        "chapter_id": chapter_id,
        "agent_id": PLANNER_AGENT_ID,
        "status": "planned",
        "current_goal": goal,
        "current_plan": [step["title"] for step in steps],
        "steps": steps,
        "tool_calls": [step["tool_call"] for step in steps if step.get("tool_call")],
        "intermediate_results": [],
        "errors": [],
        "reflection": [],
        "recovery_suggestions": [],
        "final_output": {"status": "planned", "message": "Planner 已生成制作任务计划。"},
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
    }


def planner_run_from_payload(
    *,
    project_id: str,
    payload: dict[str, Any],
    registered_tools: set[str],
) -> dict[str, Any]:
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        return build_production_planner_run(
            project_id=project_id,
            payload=payload,
            registered_tools=registered_tools,
        )
    normalized_steps = [_normalize_step(item, index) for index, item in enumerate(steps, start=1)]
    _validate_planner_steps(normalized_steps, registered_tools=registered_tools)
    now = _now()
    goal = str(payload.get("goal") or payload.get("current_goal") or "制作任务").strip()
    return {
        "run_id": str(payload.get("run_id") or f"planner-{secrets.token_hex(8)}"),
        "project_id": project_id,
        "chapter_id": str(payload.get("chapter_id") or ""),
        "agent_id": PLANNER_AGENT_ID,
        "status": str(payload.get("status") or "planned"),
        "current_goal": goal,
        "current_plan": [step["title"] for step in normalized_steps],
        "steps": normalized_steps,
        "tool_calls": [step["tool_call"] for step in normalized_steps if step.get("tool_call")],
        "intermediate_results": payload.get("intermediate_results") or [],
        "errors": payload.get("errors") or [],
        "reflection": payload.get("reflection") or [],
        "recovery_suggestions": payload.get("recovery_suggestions") or [],
        "final_output": payload.get("final_output") or {"status": "planned"},
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
    }


def execute_planner_run(
    *,
    planner_run: dict[str, Any],
    registry: ToolRegistry,
    context: ToolExecutionContext,
    max_steps: int | None = None,
) -> dict[str, Any]:
    limit = max_steps if max_steps and max_steps > 0 else None
    executed_count = 0
    tool_results: list[dict[str, Any]] = list(planner_run.get("tool_results") or [])
    steps = [dict(step) for step in planner_run.get("steps") or []]
    for step in steps:
        if limit is not None and executed_count >= limit:
            break
        if step.get("status") in {"succeeded", "failed", "skipped", "waiting_for_user"}:
            continue
        tool_call = step.get("tool_call")
        if not isinstance(tool_call, dict):
            step["status"] = "waiting_for_user"
            step["needs_human_intervention"] = True
            continue
        result = execute_tool_plan(
            registry,
            context,
            {"tool_calls": [{**tool_call, "tool_call_id": step["step_id"]}]},
        )["tool_results"][0]
        step["status"] = "succeeded" if result["status"] == "succeeded" else "failed"
        step["tool_result"] = result
        step["updated_at"] = _now()
        tool_results.append(result)
        executed_count += 1

    status = _planner_status_from_steps(steps)
    updated = {
        **planner_run,
        "steps": steps,
        "status": status,
        "tool_results": tool_results,
        "tool_calls": tool_results,
        "errors": [item for item in tool_results if item.get("status") == "failed"],
        "recovery_suggestions": _recovery_suggestions(steps),
        "final_output": {
            "status": status,
            "executed_step_count": executed_count,
            "succeeded_count": sum(1 for item in tool_results if item.get("status") == "succeeded"),
            "failed_count": sum(1 for item in tool_results if item.get("status") == "failed"),
        },
        "updated_at": _now(),
    }
    return updated


def review_planner_run(planner_run: dict[str, Any]) -> dict[str, Any]:
    steps = [dict(step) for step in planner_run.get("steps") or []]
    failed_steps = [step for step in steps if step.get("status") == "failed"]
    pending_tool_steps = [
        step
        for step in steps
        if step.get("tool_call") and step.get("status") not in {"succeeded", "failed"}
    ]
    remaining_issues = [
        {
            "failed_step_id": step.get("step_id"),
            "title": step.get("title"),
            "message": (step.get("tool_result") or {}).get("failure") or "步骤执行失败。",
            "recovery_action": "修正输入后从失败步骤继续，或转入人工复核队列。",
        }
        for step in failed_steps
    ]
    if failed_steps:
        status = "waiting_for_user"
    elif pending_tool_steps:
        status = "running"
    else:
        status = "completed"
    return {
        "run_id": planner_run.get("run_id"),
        "project_id": planner_run.get("project_id"),
        "status": status,
        "requires_human_intervention": bool(failed_steps),
        "remaining_issues": remaining_issues,
        "recovery_suggestions": _recovery_suggestions(steps),
        "reviewed_at": _now(),
    }


def planner_run_to_memory_payload(planner_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_goal": planner_run.get("current_goal") or "",
        "current_plan": planner_run.get("current_plan") or [],
        "steps": planner_run.get("steps") or [],
        "tool_calls": planner_run.get("tool_calls") or [],
        "intermediate_results": planner_run.get("intermediate_results") or [],
        "errors": planner_run.get("errors") or [],
        "reflection": planner_run.get("reflection") or [],
        "final_output": planner_run.get("final_output") or {"status": planner_run.get("status")},
        "created_at": planner_run.get("created_at"),
    }


def _tool_step(
    *,
    step_id: str,
    title: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "title": title,
        "status": "pending",
        "kind": "tool",
        "tool_call": {
            "tool_call_id": step_id,
            "tool_name": tool_name,
            "arguments": arguments,
        },
    }


def _manual_step(*, step_id: str, title: str, rationale: str) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "title": title,
        "status": "pending",
        "kind": "checkpoint",
        "tool_call": None,
        "rationale": rationale,
    }


def _normalize_step(step: Any, index: int) -> dict[str, Any]:
    if not isinstance(step, dict):
        raise TypeError("Planner step 必须是对象")
    step_id = str(step.get("step_id") or f"planner-step-{index:04d}")
    title = str(step.get("title") or step_id)
    tool_call = step.get("tool_call")
    if tool_call is not None and not isinstance(tool_call, dict):
        raise TypeError("Planner step.tool_call 必须是对象或 null")
    return {
        **step,
        "step_id": step_id,
        "title": title,
        "status": str(step.get("status") or "pending"),
        "kind": str(step.get("kind") or ("tool" if tool_call else "checkpoint")),
        "tool_call": tool_call,
    }


def _validate_planner_steps(steps: list[dict[str, Any]], *, registered_tools: set[str]) -> None:
    for step in steps:
        tool_call = step.get("tool_call")
        if not tool_call:
            continue
        tool_name = str(tool_call.get("tool_name") or "")
        if tool_name not in registered_tools:
            raise ValueError(f"Planner step uses unregistered tool: {tool_name}")


def _planner_status_from_steps(steps: list[dict[str, Any]]) -> str:
    if any(step.get("status") == "failed" for step in steps):
        return "waiting_for_user"
    pending_tool = any(
        step.get("tool_call") and step.get("status") not in {"succeeded", "failed"}
        for step in steps
    )
    if pending_tool:
        return "running"
    manual_checkpoint = any(
        not step.get("tool_call") and step.get("status") in {"pending", "waiting_for_user"}
        for step in steps
    )
    return "waiting_for_user" if manual_checkpoint else "completed"


def _quality_arguments(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "chapters": payload.get("chapters") if isinstance(payload.get("chapters"), list) else [],
        "roles": payload.get("roles") if isinstance(payload.get("roles"), list) else [],
        "utterances_by_paragraph": payload.get("utterances_by_paragraph")
        if isinstance(payload.get("utterances_by_paragraph"), dict)
        else {},
        "max_utterance_chars": int(payload.get("max_utterance_chars") or 120),
    }


def _first_long_text(payload: dict[str, Any], *, max_chars: int) -> str:
    explicit = str(payload.get("text") or "")
    if explicit:
        return explicit
    groups = payload.get("utterances_by_paragraph")
    if isinstance(groups, dict):
        for utterances in groups.values():
            if not isinstance(utterances, list):
                continue
            for utterance in utterances:
                if not isinstance(utterance, dict):
                    continue
                text = str(utterance.get("text") or "")
                if len(text) > max_chars:
                    return text
    return ""


def _recovery_suggestions(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "step_id": step.get("step_id"),
            "title": step.get("title"),
            "action": "fix_inputs_or_resume",
            "message": "修正输入后从失败步骤继续，或暂停等待人工介入。",
        }
        for step in steps
        if step.get("status") == "failed"
    ]


def _now() -> str:
    return datetime.now(UTC).isoformat()
