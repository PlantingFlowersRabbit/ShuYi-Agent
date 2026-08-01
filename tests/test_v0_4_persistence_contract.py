from __future__ import annotations

import sqlite3


def test_v0_4_sqlite_uses_wal_and_survives_repository_restart(tmp_path):
    """Covers v0.4 SQLite WAL mode and durable workflow-state persistence."""
    from backend.app.repositories.sqlite import SQLiteRepository

    db_path = tmp_path / "shuyi.sqlite3"
    first = SQLiteRepository(db_path)
    first.initialize()
    first.save_workflow(
        "workflow-001",
        {
            "mode": "step",
            "status": "awaiting_confirmation",
            "active_agent": "role_analyzer",
        },
    )
    first.save_agent_run(
        run_id="agent-run-001",
        agent_id="role_analyzer",
        status="waiting_for_roles",
        checkpoint={"chapter_id": "chapter-0001"},
    )
    first.append_event(
        run_id="agent-run-001",
        sequence=1,
        event_type="role_selected",
        payload={"dubbing_segment_id": "segment-001"},
    )
    first.close()

    with sqlite3.connect(db_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode.lower() == "wal"

    restarted = SQLiteRepository(db_path)
    restarted.initialize()
    assert restarted.get_workflow("workflow-001") == {
        "mode": "step",
        "status": "awaiting_confirmation",
        "active_agent": "role_analyzer",
    }
    assert restarted.get_agent_run("agent-run-001")["checkpoint"] == {"chapter_id": "chapter-0001"}
    assert restarted.list_events("agent-run-001") == [
        {
            "id": 1,
            "event": "role_selected",
            "data": {"dubbing_segment_id": "segment-001"},
        }
    ]
    restarted.close()
