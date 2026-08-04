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
            connection.execute(
                """
            CREATE TABLE IF NOT EXISTS agent_run_traces (
                run_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                chapter_id TEXT,
                trace_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, agent_id)
            )
            """
            )
            connection.execute(
                """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                project_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
            )
            connection.execute(
                """
            CREATE TABLE IF NOT EXISTS story_memory_chunks (
                chunk_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chunk_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
            )
            connection.execute(
                """
            CREATE TABLE IF NOT EXISTS story_bible_facts (
                fact_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                fact_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
            )
            connection.execute(
                """
            CREATE TABLE IF NOT EXISTS run_memories (
                run_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                memory_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, project_id)
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

    def save_agent_trace(self, trace: dict[str, Any]) -> None:
        run_id = str(trace.get("run_id") or "").strip()
        agent_id = str(trace.get("agent_id") or "").strip()
        if not run_id or not agent_id:
            raise ValueError("Agent trace requires run_id and agent_id")
        now = datetime.now(UTC).isoformat()
        payload = dict(trace)
        payload.setdefault("project_id", "default")
        payload.setdefault("created_at", now)
        payload["updated_at"] = now
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
            INSERT INTO agent_run_traces
                (run_id, agent_id, project_id, chapter_id, trace_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, agent_id) DO UPDATE SET
                project_id = excluded.project_id,
                chapter_id = excluded.chapter_id,
                trace_json = excluded.trace_json,
                updated_at = excluded.updated_at
            """,
                (
                    run_id,
                    agent_id,
                    str(payload.get("project_id") or "default"),
                    str(payload.get("chapter_id") or ""),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    str(payload.get("created_at") or now),
                    now,
                ),
            )
            connection.commit()

    def list_agent_traces(
        self,
        *,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT trace_json
            FROM agent_run_traces
        """
        params: list[Any] = []
        if project_id:
            sql += " WHERE project_id = ?"
            params.append(project_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self._lock:
            rows = self._require_connection().execute(sql, params).fetchall()
        return [self._decode_trace(row[0]) for row in rows]

    def get_agent_trace(self, run_id: str, *, agent_id: str | None = None) -> dict[str, Any] | None:
        params: list[Any] = [run_id]
        sql = """
            SELECT trace_json
            FROM agent_run_traces
            WHERE run_id = ?
        """
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        sql += " ORDER BY updated_at DESC LIMIT 1"
        with self._lock:
            row = self._require_connection().execute(sql, params).fetchone()
        if row is None:
            return None
        return self._decode_trace(row[0])

    def save_project(self, project: dict[str, Any]) -> None:
        project_id = str(project.get("project_id") or "").strip()
        if not project_id:
            raise ValueError("Project requires project_id")
        now = datetime.now(UTC).isoformat()
        payload = dict(project)
        payload.setdefault("created_at", now)
        payload["updated_at"] = now
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
            INSERT INTO projects (project_id, project_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                project_json = excluded.project_json,
                updated_at = excluded.updated_at
            """,
                (
                    project_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    str(payload.get("created_at") or now),
                    now,
                ),
            )
            connection.commit()

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = (
                self._require_connection()
                .execute("SELECT project_json FROM projects WHERE project_id = ?", (project_id,))
                .fetchone()
            )
        if row is None:
            return None
        return self._decode_project(row[0])

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = (
                self._require_connection()
                .execute("SELECT project_json FROM projects ORDER BY updated_at DESC")
                .fetchall()
            )
        return [self._decode_project(row[0]) for row in rows]

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM story_memory_chunks WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM story_bible_facts WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM run_memories WHERE project_id = ?", (project_id,))
            connection.commit()
        return cursor.rowcount > 0

    def save_story_bible_fact(self, *, project_id: str, fact: dict[str, Any]) -> None:
        fact_id = str(fact.get("fact_id") or "").strip()
        if not fact_id:
            raise ValueError("Story Bible fact requires fact_id")
        now = datetime.now(UTC).isoformat()
        payload = dict(fact)
        payload["project_id"] = project_id
        payload["updated_at"] = now
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
            INSERT INTO story_bible_facts (fact_id, project_id, fact_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(fact_id) DO UPDATE SET
                project_id = excluded.project_id,
                fact_json = excluded.fact_json,
                updated_at = excluded.updated_at
            """,
                (
                    fact_id,
                    project_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            connection.commit()

    def replace_story_memory(
        self,
        *,
        project_id: str,
        chunks: list[dict[str, Any]],
        facts: list[dict[str, Any]],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            connection = self._require_connection()
            connection.execute("DELETE FROM story_memory_chunks WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM story_bible_facts WHERE project_id = ?", (project_id,))
            connection.executemany(
                """
            INSERT INTO story_memory_chunks (chunk_id, project_id, chunk_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
                [
                    (
                        str(chunk["chunk_id"]),
                        project_id,
                        json.dumps(chunk, ensure_ascii=False, separators=(",", ":")),
                        now,
                    )
                    for chunk in chunks
                ],
            )
            connection.executemany(
                """
            INSERT INTO story_bible_facts (fact_id, project_id, fact_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
                [
                    (
                        str(fact["fact_id"]),
                        project_id,
                        json.dumps(fact, ensure_ascii=False, separators=(",", ":")),
                        now,
                    )
                    for fact in facts
                ],
            )
            connection.commit()

    def list_story_memory_chunks(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = (
                self._require_connection()
                .execute(
                    "SELECT chunk_json FROM story_memory_chunks WHERE project_id = ? ORDER BY updated_at DESC",
                    (project_id,),
                )
                .fetchall()
            )
        return [self._decode_chunk(row[0]) for row in rows]

    def list_story_bible_facts(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = (
                self._require_connection()
                .execute(
                    "SELECT fact_json FROM story_bible_facts WHERE project_id = ? ORDER BY updated_at DESC",
                    (project_id,),
                )
                .fetchall()
            )
        return [self._decode_fact(row[0]) for row in rows]

    def update_story_bible_fact(
        self,
        *,
        project_id: str,
        fact_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        facts = self.list_story_bible_facts(project_id)
        found = next((fact for fact in facts if fact.get("fact_id") == fact_id), None)
        if found is None:
            return None
        allowed = {"confidence", "notes", "metadata"}
        updated = {**found, **{key: value for key, value in updates.items() if key in allowed}}
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._require_connection().execute(
                """
            UPDATE story_bible_facts SET fact_json = ?, updated_at = ?
            WHERE project_id = ? AND fact_id = ?
            """,
                (
                    json.dumps(updated, ensure_ascii=False, separators=(",", ":")),
                    now,
                    project_id,
                    fact_id,
                ),
            )
            self._require_connection().commit()
        return updated

    def save_run_memory(self, memory: dict[str, Any]) -> None:
        run_id = str(memory.get("run_id") or "").strip()
        project_id = str(memory.get("project_id") or "").strip()
        if not run_id or not project_id:
            raise ValueError("Run memory requires run_id and project_id")
        now = datetime.now(UTC).isoformat()
        payload = dict(memory)
        payload["updated_at"] = now
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
            INSERT INTO run_memories (run_id, project_id, memory_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id, project_id) DO UPDATE SET
                memory_json = excluded.memory_json,
                updated_at = excluded.updated_at
            """,
                (
                    run_id,
                    project_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            connection.commit()

    def get_run_memory(self, *, project_id: str, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = (
                self._require_connection()
                .execute(
                    """
                SELECT memory_json FROM run_memories
                WHERE project_id = ? AND run_id = ?
                """,
                    (project_id, run_id),
                )
                .fetchone()
            )
        if row is None:
            return None
        return self._decode_run_memory(row[0])

    def _decode_trace(self, trace_json: str) -> dict[str, Any]:
        payload = json.loads(trace_json)
        if not isinstance(payload, dict):
            raise TypeError("Agent trace payload is not an object")
        return payload

    def _decode_project(self, project_json: str) -> dict[str, Any]:
        payload = json.loads(project_json)
        if not isinstance(payload, dict):
            raise TypeError("Project payload is not an object")
        return payload

    def _decode_chunk(self, chunk_json: str) -> dict[str, Any]:
        payload = json.loads(chunk_json)
        if not isinstance(payload, dict):
            raise TypeError("Story memory chunk payload is not an object")
        return payload

    def _decode_fact(self, fact_json: str) -> dict[str, Any]:
        payload = json.loads(fact_json)
        if not isinstance(payload, dict):
            raise TypeError("Story Bible fact payload is not an object")
        return payload

    def _decode_run_memory(self, memory_json: str) -> dict[str, Any]:
        payload = json.loads(memory_json)
        if not isinstance(payload, dict):
            raise TypeError("Run memory payload is not an object")
        return payload

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("SQLite 仓储尚未初始化")
        return self._connection
