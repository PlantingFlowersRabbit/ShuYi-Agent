from __future__ import annotations

from fastapi.testclient import TestClient


def _create_project(client: TestClient) -> str:
    return client.post("/api/v1/projects", json={"name": "长句拆分项目"}).json()["project"][
        "project_id"
    ]


def _utterance_payload(text: str) -> dict:
    return {
        "utterances_by_paragraph": {
            "p-0001": [
                {
                    "utterance_id": "p-0001-u-001",
                    "paragraph_id": "p-0001",
                    "text": text,
                    "speaker_role_id": "role-narrator",
                    "speaker_name": "旁白",
                    "audio_status": "failed",
                    "audio_error": "当前台词文本长度超过本地 TTS 单条上限。",
                    "needs_human_review": True,
                }
            ]
        },
        "max_utterance_chars": 12,
    }


def test_v0_66_detects_and_splits_long_utterance_with_text_conservation(monkeypatch, tmp_path):
    """Long text splitting keeps original text order and stable utterance ids."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    original = "林舟推门而入，屋内烛火微晃。她压低声音说，今晚不能再等。"

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        detected = client.post(
            f"/api/v1/projects/{project_id}/utterances/long-text/detect",
            json=_utterance_payload(original),
        )
        assert detected.status_code == 200
        assert detected.json()["items"][0]["utterance_id"] == "p-0001-u-001"
        assert detected.json()["items"][0]["char_count"] == len(original)

        split = client.post(
            f"/api/v1/projects/{project_id}/utterances/p-0001-u-001/split-long-text",
            json=_utterance_payload(original),
        )

    assert split.status_code == 200
    data = split.json()
    segments = data["utterances_by_paragraph"]["p-0001"]
    assert [item["utterance_id"] for item in segments] == [
        "p-0001-u-001",
        "p-0001-u-001-s002",
        "p-0001-u-001-s003",
        "p-0001-u-001-s004",
    ]
    assert "".join(item["text"] for item in segments) == original
    assert all(len(item["text"]) <= 12 for item in segments)
    assert all(item["audio_status"] == "pending_retry" for item in segments)
    assert data["split_report"]["text_conservation"]["matches"] is True


def test_v0_66_merges_split_utterances_back_to_original_text(monkeypatch, tmp_path):
    """Merge keeps the first utterance id stable and reports conservation."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    original = "第一句很长，需要拆开。第二句仍然属于同一段。"

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        split = client.post(
            f"/api/v1/projects/{project_id}/utterances/p-0001-u-001/split-long-text",
            json=_utterance_payload(original),
        ).json()
        ids = [item["utterance_id"] for item in split["utterances_by_paragraph"]["p-0001"]]

        merged = client.post(
            f"/api/v1/projects/{project_id}/utterances/merge",
            json={
                "utterances_by_paragraph": split["utterances_by_paragraph"],
                "paragraph_id": "p-0001",
                "utterance_ids": ids,
            },
        )

    assert merged.status_code == 200
    data = merged.json()
    merged_items = data["utterances_by_paragraph"]["p-0001"]
    assert len(merged_items) == 1
    assert merged_items[0]["utterance_id"] == "p-0001-u-001"
    assert merged_items[0]["text"] == original
    assert merged_items[0]["audio_status"] == "pending_retry"
    assert data["merge_report"]["text_conservation"]["matches"] is True


def test_v0_66_bulk_role_update_and_retry_queue(monkeypatch, tmp_path):
    """Dialogue editing can batch change roles and prepare failed lines for retry."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    payload = _utterance_payload("短台词")

    with TestClient(create_app()) as client:
        project_id = _create_project(client)
        updated = client.post(
            f"/api/v1/projects/{project_id}/utterances/bulk-role",
            json={
                **payload,
                "utterance_ids": ["p-0001-u-001"],
                "role_id": "role-hero",
                "speaker_name": "林舟",
            },
        )
        assert updated.status_code == 200
        utterance = updated.json()["utterances_by_paragraph"]["p-0001"][0]
        assert utterance["speaker_role_id"] == "role-hero"
        assert utterance["speaker_name"] == "林舟"
        assert utterance["needs_human_review"] is False

        retry = client.post(
            f"/api/v1/projects/{project_id}/utterances/retry-queue",
            json=updated.json(),
        )

    assert retry.status_code == 200
    data = retry.json()
    retry_item = data["utterances_by_paragraph"]["p-0001"][0]
    assert retry_item["audio_status"] == "pending_retry"
    assert retry_item["audio_error"] == ""
    assert data["retry_items"] == [{"paragraph_id": "p-0001", "utterance_id": "p-0001-u-001"}]
