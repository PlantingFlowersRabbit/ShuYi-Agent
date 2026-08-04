from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

SENSITIVE_KEY_PARTS = ("api_key", "token", "password", "secret", "authorization")


class ToolRegistryError(RuntimeError):
    pass


class UnknownToolError(ToolRegistryError):
    pass


class ToolValidationError(ToolRegistryError):
    pass


class ToolPermissionError(ToolRegistryError):
    pass


@dataclass(frozen=True)
class ToolExecutionContext:
    project_id: str


ToolImplementation = Callable[[ToolExecutionContext, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission_scope: str
    timeout_seconds: int
    implementation: ToolImplementation

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "permission_scope": self.permission_scope,
            "timeout_seconds": self.timeout_seconds,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if not definition.tool_name.strip():
            raise ToolValidationError("tool_name cannot be empty")
        self._definitions[definition.tool_name] = definition

    def get(self, tool_name: str) -> ToolDefinition:
        try:
            return self._definitions[tool_name]
        except KeyError:
            raise UnknownToolError(f"Unregistered tool: {tool_name}") from None

    def list_definitions(self) -> list[dict[str, Any]]:
        return [
            definition.to_public_dict()
            for definition in sorted(self._definitions.values(), key=lambda item: item.tool_name)
        ]


def execute_tool_plan(
    registry: ToolRegistry,
    context: ToolExecutionContext,
    plan: dict[str, Any],
) -> dict[str, Any]:
    tool_calls = _tool_calls_from_plan(plan)
    results = [
        _execute_one_tool_call(
            registry=registry,
            context=context,
            call=call,
            index=index,
        )
        for index, call in enumerate(tool_calls, start=1)
    ]
    failed_count = sum(1 for result in results if result["status"] == "failed")
    return {
        "status": "completed_with_errors" if failed_count else "completed",
        "tool_results": results,
        "failed_count": failed_count,
        "succeeded_count": len(results) - failed_count,
    }


def summarize_tool_payload(value: Any, *, max_chars: int = 320) -> str:
    redacted = _redact_sensitive(value)
    try:
        summary = json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        summary = str(redacted)
    return summary if len(summary) <= max_chars else f"{summary[: max_chars - 1]}…"


def _execute_one_tool_call(
    *,
    registry: ToolRegistry,
    context: ToolExecutionContext,
    call: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    tool_name = str(call.get("tool_name") or "").strip()
    if not tool_name:
        raise ToolValidationError("tool_call requires tool_name")
    arguments = call.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ToolValidationError(f"{tool_name} arguments must be an object")

    definition = registry.get(tool_name)
    _validate_project_scope(context=context, arguments=arguments)
    _validate_arguments(tool_name=tool_name, schema=definition.input_schema, arguments=arguments)

    started = time.perf_counter()
    try:
        result = definition.implementation(context, arguments)
        status = "succeeded"
        failure = None
    except Exception as exc:  # noqa: BLE001 - tool failures must be returned to the Agent trace.
        result = {}
        status = "failed"
        failure = str(exc)
    duration_ms = int((time.perf_counter() - started) * 1000)
    sanitized_arguments = _redact_sensitive(arguments)
    sanitized_result = _redact_sensitive(result)
    return {
        "tool_call_id": str(call.get("tool_call_id") or f"tool-call-{index:04d}"),
        "tool_name": tool_name,
        "status": status,
        "permission_scope": definition.permission_scope,
        "arguments": sanitized_arguments,
        "arguments_summary": summarize_tool_payload(sanitized_arguments),
        "result": sanitized_result,
        "output_summary": summarize_tool_payload(sanitized_result),
        "failure": failure,
        "duration_ms": duration_ms,
    }


def _tool_calls_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        raise ToolValidationError("tool plan must be an object")
    if "tool_calls" in plan:
        tool_calls = plan["tool_calls"]
        if not isinstance(tool_calls, list) or not tool_calls:
            raise ToolValidationError("tool_calls must be a non-empty list")
        if not all(isinstance(call, dict) for call in tool_calls):
            raise ToolValidationError("each tool_call must be an object")
        return tool_calls
    if "tool_name" in plan:
        return [{"tool_name": plan["tool_name"], "arguments": plan.get("arguments") or {}}]
    raise ToolValidationError("tool plan requires tool_name or tool_calls")


def _validate_project_scope(
    *,
    context: ToolExecutionContext,
    arguments: dict[str, Any],
) -> None:
    requested_project = str(arguments.get("project_id") or "").strip()
    if requested_project and requested_project != context.project_id:
        raise ToolPermissionError(
            f"tool call project_id {requested_project} does not match current project_id {context.project_id}"
        )


def _validate_arguments(
    *,
    tool_name: str,
    schema: dict[str, Any],
    arguments: dict[str, Any],
) -> None:
    required = schema.get("required") or []
    for name in required:
        if name not in arguments or arguments.get(name) in (None, ""):
            raise ToolValidationError(f"{tool_name} missing required argument: {name}")
    properties = schema.get("properties") or {}
    for name, value in arguments.items():
        if name not in properties or value is None:
            continue
        expected = properties[name].get("type")
        if expected and not _matches_json_type(value, expected):
            raise ToolValidationError(f"{tool_name}.{name} must be {expected}")


def _matches_json_type(value: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(_matches_json_type(value, item) for item in expected)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in SENSITIVE_KEY_PARTS):
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value
