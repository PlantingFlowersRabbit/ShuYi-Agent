from __future__ import annotations

from fastapi.testclient import TestClient


def _tool_memory_payload() -> dict:
    return {
        "chapters": [
            {
                "chapter_id": "chapter-0001",
                "title": "第一章",
                "paragraphs": [
                    {
                        "paragraph_id": "p-0001",
                        "text": "林舟又被称为小舟。玄衡城是他的故乡。",
                    }
                ],
            }
        ],
        "glossary": [{"term": "玄衡", "pronunciation": "xuan heng", "source_id": "glossary-001"}],
        "roles": [
            {
                "role_id": "role-linzhou",
                "name": "林舟",
                "aliases": ["小舟"],
                "profile": "压低声音的青年主角",
                "voice_resource_id": "voice-001",
            }
        ],
    }


def test_v0_63_tool_registry_validates_schema_permissions_and_unknown_tools():
    """Tool Registry exposes schemas, validates JSON-plan calls, and rejects unsafe calls."""
    from backend.app.domain.tool_registry import (
        ToolDefinition,
        ToolExecutionContext,
        ToolPermissionError,
        ToolRegistry,
        ToolValidationError,
        UnknownToolError,
        execute_tool_plan,
    )

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            tool_name="echo_memory",
            description="Echo a query for tests.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "project_id": {"type": "string"},
                },
            },
            output_schema={"type": "object", "properties": {"echo": {"type": "string"}}},
            permission_scope="project:read",
            timeout_seconds=3,
            implementation=lambda context, arguments: {
                "project_id": context.project_id,
                "echo": arguments["query"],
            },
        )
    )

    context = ToolExecutionContext(project_id="project-a")
    result = execute_tool_plan(
        registry,
        context,
        {"tool_calls": [{"tool_name": "echo_memory", "arguments": {"query": "林舟"}}]},
    )

    assert result["status"] == "completed"
    assert result["tool_results"][0]["status"] == "succeeded"
    assert result["tool_results"][0]["result"] == {"project_id": "project-a", "echo": "林舟"}
    definition = registry.list_definitions()[0]
    assert definition["tool_name"] == "echo_memory"
    assert definition["permission_scope"] == "project:read"
    assert definition["timeout_seconds"] == 3
    assert "implementation" not in definition

    try:
        execute_tool_plan(
            registry,
            context,
            {"tool_calls": [{"tool_name": "echo_memory", "arguments": {}}]},
        )
    except ToolValidationError as exc:
        assert "query" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("missing required argument should fail")

    try:
        execute_tool_plan(
            registry,
            context,
            {"tool_calls": [{"tool_name": "echo_memory", "arguments": {"query": "x", "project_id": "project-b"}}]},
        )
    except ToolPermissionError as exc:
        assert "project_id" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("cross-project tool call should fail")

    try:
        execute_tool_plan(
            registry,
            context,
            {"tool_calls": [{"tool_name": "run_python", "arguments": {}}]},
        )
    except UnknownToolError as exc:
        assert "run_python" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("unregistered tool should fail")


def test_v0_63_fastapi_executes_project_scoped_tool_plan_and_records_trace(
    monkeypatch, tmp_path
):
    """Tool calls are project-scoped, executable through JSON-plan fallback, and traceable."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))

    from backend.app.api import app as app_module

    monkeypatch.setattr(
        app_module,
        "_fetch_tts_health",
        lambda base_url: {
            "ok": True,
            "voice_clone": True,
            "voice_design": True,
            "voice_design_capable": True,
            "reachable": True,
            "ready": True,
            "health_url": f"{base_url.rstrip('/')}/health",
        },
    )

    with TestClient(app_module.create_app()) as client:
        project_a = client.post("/api/v1/projects", json={"name": "工具项目 A"}).json()[
            "project"
        ]["project_id"]
        project_b = client.post("/api/v1/projects", json={"name": "工具项目 B"}).json()[
            "project"
        ]["project_id"]
        client.post(f"/api/v1/projects/{project_a}/memory/index", json=_tool_memory_payload())

        definitions = client.get("/api/v1/tools")
        assert definitions.status_code == 200
        tool_names = {tool["tool_name"] for tool in definitions.json()["tools"]}
        assert {
            "search_story_memory",
            "get_project_status",
            "list_roles",
            "get_role_profile",
            "query_utterances",
            "suggest_long_text_split",
            "check_text_conservation",
            "check_tts_health",
            "generate_voice_preview",
            "lookup_pronunciation",
        }.issubset(tool_names)

        payload = {
            "run_id": "tool-run-001",
            "agent_id": "role_analyzer",
            "chapter_id": "chapter-0001",
            "tool_calls": [
                {"tool_name": "search_story_memory", "arguments": {"query": "小舟", "top_k": 2}},
                {"tool_name": "lookup_pronunciation", "arguments": {"term": "玄衡"}},
                {
                    "tool_name": "get_project_status",
                    "arguments": {
                        "chapters": [
                            {
                                "chapter_id": "chapter-0001",
                                "paragraphs": [{"paragraph_id": "p-0001", "text": "正文"}],
                            }
                        ],
                        "roles": [{"role_id": "role-linzhou", "name": "林舟", "voice_resource_id": ""}],
                        "utterances_by_paragraph": {},
                    },
                },
                {
                    "tool_name": "query_utterances",
                    "arguments": {
                        "utterances_by_paragraph": {
                            "p-0001": [
                                {
                                    "utterance_id": "u-001",
                                    "paragraph_id": "p-0001",
                                    "text": "需要复核。",
                                    "needs_human_review": True,
                                }
                            ]
                        },
                        "status": "needs_human_review",
                    },
                },
                {
                    "tool_name": "suggest_long_text_split",
                    "arguments": {"text": "第一句。第二句。第三句。", "max_chars": 4},
                },
                {
                    "tool_name": "check_text_conservation",
                    "arguments": {"original_text": "甲乙丙", "segments": ["甲", "乙丙"]},
                },
                {"tool_name": "check_tts_health", "arguments": {}},
                {
                    "tool_name": "generate_voice_preview",
                    "arguments": {"name": "林舟试听", "description": "压低声音", "dry_run": True},
                },
            ],
        }
        executed = client.post(f"/api/v1/projects/{project_a}/tools/execute", json=payload)
        assert executed.status_code == 200
        data = executed.json()
        assert data["status"] == "completed"
        assert [item["status"] for item in data["tool_results"]] == ["succeeded"] * 8
        assert data["tool_results"][0]["result"]["results"][0]["citation"]["source_id"] == "chapter-0001:p-0001"
        assert data["tool_results"][1]["result"]["facts"][0]["object"] == "xuan heng"
        assert data["tool_results"][2]["result"]["quality_report"]["summary"]["unsegmented"] == 1
        assert data["tool_results"][3]["result"]["total_count"] == 1
        assert data["tool_results"][4]["result"]["text_conservation"]["matches"] is True
        assert data["tool_results"][5]["result"]["matches"] is True
        assert data["tool_results"][6]["result"]["ready"] is True
        assert data["tool_results"][7]["result"]["status"] == "dry_run"

        detail = client.get("/api/v1/agent-runs/tool-run-001?agent_id=role_analyzer")
        assert detail.status_code == 200
        trace = detail.json()["trace"]
        assert trace["tool_calls"][0]["tool_name"] == "search_story_memory"
        assert trace["tool_calls"][0]["arguments_summary"]
        assert trace["tool_calls"][0]["output_summary"]
        assert trace["tool_calls"][0]["duration_ms"] >= 0
        assert "api_key" not in str(trace).lower()

        unknown = client.post(
            f"/api/v1/projects/{project_a}/tools/execute",
            json={"tool_calls": [{"tool_name": "run_python", "arguments": {}}]},
        )
        assert unknown.status_code == 404

        cross_project = client.post(
            f"/api/v1/projects/{project_a}/tools/execute",
            json={
                "tool_calls": [
                    {
                        "tool_name": "list_roles",
                        "arguments": {"project_id": project_b},
                    }
                ]
            },
        )
        assert cross_project.status_code == 403

        isolated_search = client.post(
            f"/api/v1/projects/{project_b}/tools/execute",
            json={
                "tool_name": "search_story_memory",
                "arguments": {"query": "小舟"},
            },
        )
        assert isolated_search.status_code == 200
        assert isolated_search.json()["tool_results"][0]["result"]["results"] == []
