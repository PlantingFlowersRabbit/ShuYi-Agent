from __future__ import annotations

from dataclasses import asdict
from typing import Any

from backend.app.domain.audio import VoiceJob
from backend.app.domain.novel import Chapter, ChapterWorkbench, ParagraphModule
from backend.app.domain.roles import RoleCollection
from backend.app.domain.voices import VoiceResourceCollection
from backend.app.repositories.sqlite import SQLiteRepository

SNAPSHOT_ID = "application"


def serialize_runtime_state(state: dict[str, Any]) -> dict[str, Any]:
    """把可恢复的业务状态转换为不包含密钥和宿主机对象的 JSON。"""
    workbenches: dict[str, Any] = {}
    for chapter_id, workbench in state["workbenches"].items():
        workbenches[chapter_id] = {
            "chapter": asdict(workbench.chapter),
            "paragraphs": [asdict(paragraph) for paragraph in workbench._paragraphs],
            "confirmed": bool(workbench._confirmed),
        }
    model_config = {
        section: {key: value for key, value in values.items() if key != "api_key"}
        for section, values in state["model_config"].items()
    }
    return {
        "chapters": [asdict(chapter) for chapter in state["chapters"]],
        "workbenches": workbenches,
        "roles": [role.to_dict() for role in state["roles"].list()],
        "voices": [voice.to_dict() for voice in state["voices"].list()],
        "voice_jobs": {job_id: job.to_dict() for job_id, job in state["voice_jobs"].items()},
        "model_config": model_config,
    }


def restore_runtime_state(state: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """在保持运行时服务对象的同时恢复 SQLite 中的业务快照。"""
    if not snapshot:
        return state
    chapters = [Chapter(**item) for item in snapshot.get("chapters", [])]
    workbenches: dict[str, ChapterWorkbench] = {}
    for chapter_id, item in snapshot.get("workbenches", {}).items():
        workbench = ChapterWorkbench(
            Chapter(**item["chapter"]),
            [ParagraphModule(**paragraph) for paragraph in item.get("paragraphs", [])],
        )
        workbench._confirmed = bool(item.get("confirmed", False))
        workbenches[chapter_id] = workbench
    state.update(
        {
            "chapters": chapters,
            "workbenches": workbenches,
            "roles": RoleCollection(snapshot.get("roles", [])),
            "voices": VoiceResourceCollection(snapshot.get("voices", [])),
            "voice_jobs": {
                job_id: VoiceJob(**job) for job_id, job in snapshot.get("voice_jobs", {}).items()
            },
            "model_config": {
                **state["model_config"],
                **snapshot.get("model_config", {}),
            },
        }
    )
    return state


def save_runtime_state(repository: SQLiteRepository, state: dict[str, Any]) -> None:
    repository.save_workflow(SNAPSHOT_ID, serialize_runtime_state(state))
