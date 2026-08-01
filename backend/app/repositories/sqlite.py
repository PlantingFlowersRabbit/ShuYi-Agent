from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SQLiteRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def initialize(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            if str(self.path) != ":memory:":
                self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.path), check_same_thread=False)
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
            connection.execute(
                """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                checkpoint_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
            )
            connection.execute(
                """
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, sequence)
            )
            """
            )
            connection.commit()
            self._connection = connection

    def save_workflow(self, workflow_id: str, state: dict[str, Any]) -> None:
        with self._lock:
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
        with self._lock:
            row = (
                self._require_connection()
                .execute("SELECT state_json FROM workflows WHERE workflow_id = ?", (workflow_id,))
                .fetchone()
            )
        if row is None:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, dict):
            raise TypeError(f"工作流快照不是对象：{workflow_id}")
        return payload

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def ping(self) -> bool:
        with self._lock:
            row = self._require_connection().execute("SELECT 1").fetchone()
        return bool(row and row[0] == 1)

    def save_agent_run(
        self,
        *,
        run_id: str,
        agent_id: str,
        status: str,
        checkpoint: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
            INSERT INTO agent_runs (run_id, agent_id, status, checkpoint_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                agent_id = excluded.agent_id,
                status = excluded.status,
                checkpoint_json = excluded.checkpoint_json,
                updated_at = excluded.updated_at
            """,
                (
                    run_id,
                    agent_id,
                    status,
                    json.dumps(checkpoint, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            connection.commit()

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = (
                self._require_connection()
                .execute(
                    """
                SELECT agent_id, status, checkpoint_json, updated_at
                FROM agent_runs WHERE run_id = ?
                """,
                    (run_id,),
                )
                .fetchone()
            )
        if row is None:
            return None
        checkpoint = json.loads(row[2])
        if not isinstance(checkpoint, dict):
            raise TypeError(f"Agent 运行检查点不是对象：{run_id}")
        return {
            "run_id": run_id,
            "agent_id": row[0],
            "status": row[1],
            "checkpoint": checkpoint,
            "updated_at": row[3],
        }

    def append_event(
        self,
        *,
        run_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
            INSERT OR IGNORE INTO events
                (run_id, sequence, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
                (
                    run_id,
                    sequence,
                    event_type,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()

    def list_events(self, run_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            rows = (
                self._require_connection()
                .execute(
                    """
                SELECT sequence, event_type, payload_json
                FROM events
                WHERE run_id = ? AND sequence > ?
                ORDER BY sequence
                """,
                    (run_id, after_sequence),
                )
                .fetchall()
            )
        events: list[dict[str, Any]] = []
        for sequence, event_type, payload_json in rows:
            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                raise TypeError(f"Agent 事件数据不是对象：{run_id}/{sequence}")
            events.append({"id": sequence, "event": event_type, "data": payload})
        return events

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("SQLite 仓储尚未初始化")
        return self._connection
