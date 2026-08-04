from __future__ import annotations

from fastapi.testclient import TestClient


def test_v0_60_token_context_report_estimates_budget_fields():
    """v0.6.0 records an explainable context report before an Agent run."""
    from backend.app.domain.agent_trace import build_token_context_report

    report = build_token_context_report(
        system_prompt="你是书弈 Agent，只返回严格 JSON。",
        input_text="林舟说：“先别急。”旁白继续描述场景。",
        output_text='{"role_candidates":[]}',
        context_window=4096,
        reserved_output_tokens=512,
        rag_evidence_tokens=128,
    )

    assert report["estimated_prompt_tokens"] > 0
    assert report["estimated_input_tokens"] > 0
    assert report["estimated_output_tokens"] > 0
    assert report["estimated_total_tokens"] == (
        report["estimated_prompt_tokens"]
        + report["estimated_input_tokens"]
        + report["estimated_output_tokens"]
        + 128
    )
    assert report["context_window"] == 4096
    assert report["reserved_output_tokens"] == 512
    assert report["available_input_tokens"] == 4096 - 512 - report["estimated_prompt_tokens"]
    assert report["within_context_window"] is True
    assert report["budget_policy"]["system_prompt"] == "preserve"
    assert report["budget_policy"]["current_chapter"] == "prioritize"
    assert report["budget_policy"]["rag_evidence"] == "cap"


def test_v0_60_sqlite_persists_agent_trace_history(tmp_path):
    """Agent traces are queryable separately from lightweight checkpoints."""
    from backend.app.repositories.sqlite import SQLiteRepository

    repository = SQLiteRepository(tmp_path / "trace.sqlite3")
    repository.initialize()
    repository.save_agent_trace(
        {
            "run_id": "agent-run-001",
            "project_id": "default",
            "chapter_id": "chapter-0001",
            "agent_id": "role_analyzer",
            "agent_name": "角色分析 Agent",
            "prompt_id": "role_analyzer",
            "prompt_version": "1",
            "prompt_sha256": "a" * 64,
            "model_name": "demo-model",
            "provider_base_url": "https://models.example.test/v1",
            "temperature": 0,
            "max_tokens": 1024,
            "estimated_prompt_tokens": 10,
            "estimated_input_tokens": 20,
            "estimated_output_tokens": 5,
            "estimated_total_tokens": 35,
            "context_window": 4096,
            "input_summary": "第一章：旁白第一段。",
            "raw_model_output": '{"role_candidates":[]}',
            "parsed_output": {"role_candidates": []},
            "validation_status": "accepted",
            "validation_errors": [],
            "reflection_count": 0,
            "reflection_trace": [],
            "final_decision": "waiting_for_roles",
            "human_review_count": 1,
            "duration_ms": 12,
            "token_context_report": {"within_context_window": True},
        }
    )

    listed = repository.list_agent_traces()
    assert len(listed) == 1
    assert listed[0]["run_id"] == "agent-run-001"
    assert listed[0]["agent_id"] == "role_analyzer"
    assert listed[0]["prompt_sha256"] == "a" * 64
    assert listed[0]["token_context_report"]["within_context_window"] is True

    detail = repository.get_agent_trace("agent-run-001", agent_id="role_analyzer")
    assert detail is not None
    assert detail["raw_model_output"] == '{"role_candidates":[]}'
    assert detail["parsed_output"] == {"role_candidates": []}
    repository.close()


def test_v0_60_fastapi_lists_agent_trace_after_role_analysis(monkeypatch, tmp_path):
    """Run History exposes prompt SHA, token report, model metadata, and parsed output."""
    from backend.app.domain.dubbing_workflow import (
        LangChainRoleAnalysisSkill,
        RoleAnalysisCandidate,
    )

    def fake_analyze_roles(self, **kwargs):
        return [
            RoleAnalysisCandidate(
                name="旁白",
                aliases=[],
                gender=None,
                profile="叙述者",
                voice_direction="沉稳清晰",
                evidence=["旁白第一段。"],
                confidence=0.9,
                needs_human_review=True,
            )
        ]

    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(LangChainRoleAnalysisSkill, "analyze_roles", fake_analyze_roles)

    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        configured = client.patch(
            "/api/v1/model-config",
            json={
                "text_model": {
                    "base_url": "https://models.example.test/v1",
                    "model": "openai-compatible-test-model",
                }
            },
        )
        assert configured.status_code == 200
        synced = client.put(
            "/api/v1/chapters/chapter-0001/paragraphs",
            json={
                "title": "第一章",
                "paragraphs": [{"paragraph_id": "p-0001", "text": "旁白第一段。"}],
                "confirm": False,
            },
        )
        assert synced.status_code == 200
        started = client.post("/api/v1/chapters/chapter-0001/agent-runs", json={})
        assert started.status_code == 200
        run_id = started.json()["thread_id"]

        history = client.get("/api/v1/agent-runs")
        assert history.status_code == 200
        traces = history.json()["runs"]
        assert traces
        assert traces[0]["run_id"] == run_id
        assert traces[0]["project_id"] == "default"
        assert traces[0]["agent_id"] == "role_analyzer"
        assert traces[0]["prompt_sha256"]
        assert traces[0]["model_name"] == "openai-compatible-test-model"
        assert traces[0]["provider_base_url"] == "https://models.example.test/v1"
        assert "api_key" not in str(traces[0]).lower()
        assert traces[0]["estimated_total_tokens"] > 0
        assert traces[0]["token_context_report"]["within_context_window"] is True

        detail = client.get(f"/api/v1/agent-runs/{run_id}?agent_id=role_analyzer")
        assert detail.status_code == 200
        trace = detail.json()["trace"]
        assert trace["parsed_output"]["role_candidates"][0]["name"] == "旁白"
        assert trace["validation_status"] == "accepted"
        assert trace["final_decision"] == "waiting_for_roles"
