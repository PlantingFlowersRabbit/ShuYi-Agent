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
    restarted.close()
