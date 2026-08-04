from __future__ import annotations

from fastapi.testclient import TestClient


def _create_project(client: TestClient) -> str:
    return client.post("/api/v1/projects", json={"name": "Planner 项目"}).json()["project"][
        "project_id"
    ]


def _quality_payload() -> dict:
    return {
        "chapters": [
            {
                "chapter_id": "chapter-0001",
                "title": "第一章",
                "paragraphs": [{"paragraph_id": "p-0001", "text": "林舟推门而入。"}],
            }
        ],
        "roles": [
            {
                "role_id": "role-linzhou",
                "name": "林舟",
                "voice_resource_id": "voice-001",
            }
        ],
        "utterances_by_paragraph": {
            "p-0001": [
                {
                    "utterance_id": "p-0001-u-001",
                    "paragraph_id": "p-0001",
                    "text": "林舟推门而入。",
                    "speaker_role_id": "role-linzhou",
                    "audio_path": "/outputs/project/audio/p-0001-u-001.wav",
                    "needs_human_review": False,
                }
            ]
        },
        "max_utterance_chars": 120,
    }


def test_v0_65_planner_generates_registered_export_plan(monkeypatch, tmp_path):
    """Planner turns an export goal into auditable registered tool steps."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        known_tools = {
            tool["tool_name"] for tool in client.get("/api/v1/tools").json()["tools"]
        }

        response = client.post(
            f"/api/v1/projects/{project_id}/planner/plan",
            json={
                "goal": "把当前章节处理到可导出",
                "chapter_id": "chapter-0001",
                **_quality_payload(),
            },
        )

        assert response.status_code == 200
        planner_run = response.json()["planner_run"]
        assert planner_run["status"] == "planned"
        assert planner_run["current_goal"] == "把当前章节处理到可导出"
        assert planner_run["chapter_id"] == "chapter-0001"
        assert [step["status"] for step in planner_run["steps"]] == ["pending"] * len(
            planner_run["steps"]
        )
        assert "运行导出前质量检查" in [step["title"] for step in planner_run["steps"]]
        assert "复盘剩余问题" in [step["title"] for step in planner_run["steps"]]
        assert {
            step["tool_call"]["tool_name"] for step in planner_run["steps"] if step["tool_call"]
        }.issubset(known_tools)

        restored = client.get(
            f"/api/v1/projects/{project_id}/run-memory/{planner_run['run_id']}"
        )
        assert restored.status_code == 200
        run_memory = restored.json()["run_memory"]
        assert run_memory["current_goal"] == "把当前章节处理到可导出"
        assert run_memory["final_output"]["status"] == "planned"


def test_v0_65_executor_runs_registered_steps_and_reviewer_completes(monkeypatch, tmp_path):
    """Executor runs planner steps through Tool Registry and reviewer checks completion."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        planned = client.post(
            f"/api/v1/projects/{project_id}/planner/plan",
            json={
                "goal": "把当前章节处理到可导出",
                "chapter_id": "chapter-0001",
                **_quality_payload(),
            },
        ).json()["planner_run"]

        executed = client.post(
            f"/api/v1/projects/{project_id}/planner/execute",
            json={"run_id": planned["run_id"], "max_steps": 3},
        )

        assert executed.status_code == 200
        run = executed.json()["planner_run"]
        assert run["status"] in {"running", "completed"}
        assert run["steps"][0]["status"] == "succeeded"
        assert run["steps"][0]["tool_result"]["tool_name"] == "get_project_status"
        assert run["steps"][1]["tool_result"]["tool_name"] == "query_utterances"

        review = client.post(
            f"/api/v1/projects/{project_id}/planner/review",
            json={"run_id": planned["run_id"]},
        )
        assert review.status_code == 200
        assert review.json()["review"]["status"] in {"running", "completed"}
        assert review.json()["review"]["remaining_issues"] == []


def test_v0_65_failed_task_is_recoverable_after_restart(monkeypatch, tmp_path):
    """Failed planner steps are persisted and reviewed with recovery guidance."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        failed = client.post(
            f"/api/v1/projects/{project_id}/planner/execute",
            json={
                "run_id": "planner-failure-001",
                "goal": "恢复失败任务",
                "steps": [
                    {
                        "step_id": "missing-role",
                        "title": "读取不存在角色",
                        "tool_call": {
                            "tool_name": "get_role_profile",
                            "arguments": {"role_id": "missing-role"},
                        },
                    }
                ],
            },
        )
        assert failed.status_code == 200
        run = failed.json()["planner_run"]
        assert run["status"] == "waiting_for_user"
        assert run["steps"][0]["status"] == "failed"
        assert run["recovery_suggestions"][0]["step_id"] == "missing-role"

    with TestClient(create_app()) as restarted:
        restored = restarted.get(
            f"/api/v1/projects/{project_id}/planner/runs/planner-failure-001"
        )
        assert restored.status_code == 200
        assert restored.json()["planner_run"]["status"] == "waiting_for_user"

        review = restarted.post(
            f"/api/v1/projects/{project_id}/planner/review",
            json={"run_id": "planner-failure-001"},
        )
        assert review.status_code == 200
        data = review.json()["review"]
        assert data["status"] == "waiting_for_user"
        assert data["requires_human_intervention"] is True
        assert data["remaining_issues"][0]["failed_step_id"] == "missing-role"
        assert "修正输入后从失败步骤继续" in data["remaining_issues"][0]["recovery_action"]
