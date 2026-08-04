from __future__ import annotations

from fastapi.testclient import TestClient


def test_v0_61_project_crud_persists_and_returns_scoped_output_roots(monkeypatch, tmp_path):
    """Project workspaces isolate metadata and generated output directories."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        initial = client.get("/api/v1/projects")
        assert initial.status_code == 200
        assert initial.json()["projects"][0]["project_id"] == "default"

        created = client.post("/api/v1/projects", json={"name": "红楼梦试制"})
        assert created.status_code == 200
        project = created.json()["project"]
        assert project["project_id"].startswith("project-")
        assert project["name"] == "红楼梦试制"
        assert project["output_roots"]["audio"].endswith(f"outputs/{project['project_id']}/audio")
        assert project["output_roots"]["exports"].endswith(
            f"outputs/{project['project_id']}/exports"
        )

    with TestClient(create_app()) as restarted:
        listed = restarted.get("/api/v1/projects")
        assert listed.status_code == 200
        ids = {item["project_id"] for item in listed.json()["projects"]}
        assert {"default", project["project_id"]}.issubset(ids)

        fetched = restarted.get(f"/api/v1/projects/{project['project_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["project"]["name"] == "红楼梦试制"

        removed = restarted.delete(f"/api/v1/projects/{project['project_id']}")
        assert removed.status_code == 200
        assert removed.json()["deleted"] is True
        assert restarted.get(f"/api/v1/projects/{project['project_id']}").status_code == 404
        assert restarted.delete("/api/v1/projects/default").status_code == 409


def test_v0_61_quality_check_counts_book_and_chapter_issues(monkeypatch, tmp_path):
    """Quality check summarizes real audiobook production blockers."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    payload = {
        "chapters": [
            {
                "chapter_id": "chapter-0001",
                "title": "第一章",
                "paragraphs": [
                    {"paragraph_id": "p-0001", "text": "还没有划分台词。"},
                    {"paragraph_id": "p-0002", "text": "已经划分。"},
                ],
            }
        ],
        "roles": [
            {"role_id": "hero", "name": "林舟", "voice_resource_id": "voice-001"},
            {"role_id": "narrator", "name": "旁白", "voice_resource_id": "voice-001"},
            {"role_id": "villain", "name": "反派", "voice_resource_id": ""},
        ],
        "utterances_by_paragraph": {
            "p-0002": [
                {
                    "utterance_id": "p-0002-u-001",
                    "paragraph_id": "p-0002",
                    "text": "这是一条需要复核并且超过长度阈值的台词。",
                    "speaker_role_id": None,
                    "speaker_name": "未知角色",
                    "confidence": 0.4,
                    "needs_human_review": True,
                },
                {
                    "utterance_id": "p-0002-u-002",
                    "paragraph_id": "p-0002",
                    "text": "尚未生成配音。",
                    "speaker_role_id": "hero",
                    "speaker_name": "林舟",
                    "needs_human_review": False,
                },
                {
                    "utterance_id": "p-0002-u-003",
                    "paragraph_id": "p-0002",
                    "text": "配音失败。",
                    "speaker_role_id": "narrator",
                    "speaker_name": "旁白",
                    "audio_status": "failed",
                    "audio_error": "TTS error",
                    "needs_human_review": False,
                },
            ]
        },
        "max_utterance_chars": 10,
    }

    with TestClient(create_app()) as client:
        project = client.post("/api/v1/projects", json={"name": "质量检查项目"}).json()[
            "project"
        ]
        response = client.post(
            f"/api/v1/projects/{project['project_id']}/quality-check",
            json=payload,
        )

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["unsegmented"] == 1
    assert summary["unselected_role"] == 1
    assert summary["undubbed"] == 1
    assert summary["dubbing_failed"] == 1
    assert summary["long_utterance"] == 1
    assert summary["duplicate_voice"] == 2
    assert summary["role_without_voice"] == 1
    assert summary["needs_human_review"] == 1
    assert response.json()["can_export"] is False
    issue_types = {issue["issue_type"] for issue in response.json()["issues"]}
    assert {
        "unsegmented",
        "unselected_role",
        "undubbed",
        "dubbing_failed",
        "long_utterance",
        "duplicate_voice",
        "role_without_voice",
        "needs_human_review",
    }.issubset(issue_types)


def test_v0_61_review_queue_filters_actionable_items(monkeypatch, tmp_path):
    """Review queue can filter centralized human-in-the-loop work."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    payload = {
        "chapters": [{"chapter_id": "chapter-0001", "title": "第一章", "paragraphs": []}],
        "roles": [{"role_id": "hero", "name": "林舟", "voice_resource_id": "voice-001"}],
        "utterances_by_paragraph": {
            "p-0001": [
                {
                    "utterance_id": "p-0001-u-001",
                    "paragraph_id": "p-0001",
                    "text": "低置信度。",
                    "speaker_role_id": "hero",
                    "speaker_name": "林舟",
                    "confidence": 0.45,
                    "needs_human_review": True,
                },
                {
                    "utterance_id": "p-0001-u-002",
                    "paragraph_id": "p-0001",
                    "text": "失败。",
                    "speaker_role_id": "hero",
                    "speaker_name": "林舟",
                    "audio_status": "failed",
                    "audio_error": "TTS error",
                },
            ]
        },
        "max_utterance_chars": 20,
    }

    with TestClient(create_app()) as client:
        project = client.post("/api/v1/projects", json={"name": "审稿队列项目"}).json()[
            "project"
        ]
        review = client.post(
            f"/api/v1/projects/{project['project_id']}/review-queue",
            json={**payload, "filters": {"issue_type": "needs_human_review"}},
        )
        failed = client.post(
            f"/api/v1/projects/{project['project_id']}/review-queue",
            json={**payload, "filters": {"issue_type": "dubbing_failed"}},
        )

    assert review.status_code == 200
    assert [item["utterance_id"] for item in review.json()["items"]] == ["p-0001-u-001"]
    assert review.json()["items"][0]["actions"] == ["jump", "confirm", "change_role"]

    assert failed.status_code == 200
    assert [item["utterance_id"] for item in failed.json()["items"]] == ["p-0001-u-002"]
    assert "retry_dubbing" in failed.json()["items"][0]["actions"]
