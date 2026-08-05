from __future__ import annotations

from fastapi.testclient import TestClient


def test_v0_72_project_workspace_state_persists_across_restart(monkeypatch, tmp_path):
    """Project workspace state stores the current production step for restoration."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        project = client.post("/api/v1/projects", json={"name": "状态保存项目"}).json()[
            "project"
        ]
        project_id = project["project_id"]
        saved = client.put(
            f"/api/v1/projects/{project_id}/workspace-state",
            json={
                "workspace_state": {
                    "active_chapter_id": "chapter-0001",
                    "has_split_chapters": True,
                    "confirmed": False,
                    "utterances_by_paragraph": {
                        "p-0001": [
                            {
                                "utteranceId": "p-0001-u-001",
                                "text": "放开我！你们是谁？快放开我！",
                            }
                        ]
                    },
                }
            },
        )
        assert saved.status_code == 200
        assert saved.json()["workspace_state"]["active_chapter_id"] == "chapter-0001"

    with TestClient(create_app()) as restarted:
        fetched = restarted.get(f"/api/v1/projects/{project_id}/workspace-state")

    assert fetched.status_code == 200
    state = fetched.json()["workspace_state"]
    assert state["has_split_chapters"] is True
    assert state["utterances_by_paragraph"]["p-0001"][0]["text"] == (
        "放开我！你们是谁？快放开我！"
    )


def test_v0_72_tts_segments_guard_repeated_short_opening_exclamation():
    """Repeated short shouted openings are synthesized as separate guarded chunks."""
    from backend.app.domain.audio import tts_synthesis_segments

    assert tts_synthesis_segments("“放开我！你们是谁？快放开我！”") == [
        "放开我！",
        "你们是谁？快放开我！",
    ]
    assert tts_synthesis_segments("你们是谁？快放开我！") == ["你们是谁？快放开我！"]
