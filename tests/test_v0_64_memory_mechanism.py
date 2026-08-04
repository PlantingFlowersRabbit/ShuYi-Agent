from __future__ import annotations

from fastapi.testclient import TestClient


def test_v0_64_story_memory_write_rules_and_prompt_context(monkeypatch, tmp_path):
    """Long-term memory promotes user corrections and keeps rejected facts out of prompts."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        project_id = client.post("/api/v1/projects", json={"name": "长期记忆项目"}).json()[
            "project"
        ]["project_id"]

        user_fact = client.post(
            f"/api/v1/projects/{project_id}/story-bible/facts",
            json={
                "subject": "林舟",
                "predicate": "alias",
                "object": "小舟",
                "writer": "user",
                "source_type": "user_correction",
                "notes": "用户确认过的别名",
            },
        )
        assert user_fact.status_code == 200
        assert user_fact.json()["fact"]["confidence"] == "user_confirmed"

        model_fact = client.post(
            f"/api/v1/projects/{project_id}/story-bible/facts",
            json={
                "subject": "林舟",
                "predicate": "identity",
                "object": "玄衡城少主",
                "writer": "model",
                "confidence": "user_confirmed",
            },
        )
        assert model_fact.status_code == 200
        assert model_fact.json()["fact"]["confidence"] == "model_suggested"

        rejected_fact = client.post(
            f"/api/v1/projects/{project_id}/story-bible/facts",
            json={
                "subject": "林舟",
                "predicate": "alias",
                "object": "假名",
                "writer": "user",
                "confidence": "rejected",
                "notes": "用户否定，保留以防重复犯错",
            },
        )
        assert rejected_fact.status_code == 200
        assert rejected_fact.json()["fact"]["confidence"] == "rejected"

        context = client.get(
            f"/api/v1/projects/{project_id}/story-bible/memory-context",
            params={"query": "林舟"},
        )
        assert context.status_code == 200
        data = context.json()
        assert [fact["object"] for fact in data["facts_for_prompt"]] == ["小舟"]
        assert [fact["object"] for fact in data["candidate_facts"]] == ["玄衡城少主"]
        assert [fact["object"] for fact in data["rejected_facts"]] == ["假名"]
        assert "假名" not in str(data["facts_for_prompt"])


def test_v0_64_short_term_run_memory_restores_after_restart(monkeypatch, tmp_path):
    """Short-term Run Memory captures goal, plan, tool calls, errors, and final output."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        project_id = client.post("/api/v1/projects", json={"name": "短期记忆项目"}).json()[
            "project"
        ]["project_id"]
        executed = client.post(
            f"/api/v1/projects/{project_id}/tools/execute",
            json={
                "run_id": "run-memory-001",
                "agent_id": "role_analyzer",
                "current_goal": "把当前章节处理到可导出",
                "current_plan": ["校验文本守恒", "记录工具结果"],
                "tool_calls": [
                    {
                        "tool_name": "check_text_conservation",
                        "arguments": {"original_text": "甲乙丙", "segments": ["甲", "乙丙"]},
                    }
                ],
            },
        )
        assert executed.status_code == 200

    with TestClient(create_app()) as restarted:
        restored = restarted.get(
            f"/api/v1/projects/{project_id}/run-memory/run-memory-001",
        )
        assert restored.status_code == 200
        memory = restored.json()["run_memory"]
        assert memory["current_goal"] == "把当前章节处理到可导出"
        assert memory["current_plan"] == ["校验文本守恒", "记录工具结果"]
        assert memory["steps"][0]["status"] == "succeeded"
        assert memory["tool_calls"][0]["tool_name"] == "check_text_conservation"
        assert memory["tool_calls"][0]["result"]["matches"] is True
        assert memory["errors"] == []
        assert memory["final_output"]["status"] == "completed"


def test_v0_64_rejected_memory_is_not_used_by_pronunciation_tool(monkeypatch, tmp_path):
    """Rejected long-term memory is retained for audit but excluded from tool facts."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        project_id = client.post("/api/v1/projects", json={"name": "读音记忆项目"}).json()[
            "project"
        ]["project_id"]
        client.post(
            f"/api/v1/projects/{project_id}/story-bible/facts",
            json={
                "subject": "玄衡",
                "predicate": "pronunciation",
                "object": "xuan heng",
                "writer": "user",
            },
        )
        client.post(
            f"/api/v1/projects/{project_id}/story-bible/facts",
            json={
                "subject": "玄衡",
                "predicate": "pronunciation",
                "object": "xuan ping",
                "writer": "user",
                "confidence": "rejected",
            },
        )

        lookup = client.post(
            f"/api/v1/projects/{project_id}/tools/execute",
            json={"tool_name": "lookup_pronunciation", "arguments": {"term": "玄衡"}},
        )

    assert lookup.status_code == 200
    facts = lookup.json()["tool_results"][0]["result"]["facts"]
    assert [fact["object"] for fact in facts] == ["xuan heng"]
