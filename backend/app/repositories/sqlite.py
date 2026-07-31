from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SQLiteRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        if self._connection is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL
            )
            """
        )
        connection.commit()
        self._connection = connection

    def save_workflow(self, workflow_id: str, state: dict[str, Any]) -> None:
        connection = self._require_connection()
        connection.execute(
            """
            INSERT INTO workflows (workflow_id, state_json) VALUES (?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET state_json = excluded.state_json
            """,
            (workflow_id, json.dumps(state, ensure_ascii=False, separators=(",", ":"))),
        )
        connection.commit()

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        row = self._require_connection().execute(
            "SELECT state_json FROM workflows WHERE workflow_id = ?", (workflow_id,)
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, dict):
            raise TypeError(f"workflow state is not an object: {workflow_id}")
        return payload

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("repository is not initialized")
        return self._connection
