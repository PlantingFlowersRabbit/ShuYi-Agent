from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_PROJECT_ID = "default"
DEFAULT_LONG_UTTERANCE_CHARS = 120
QUALITY_ISSUE_TYPES = (
    "unsegmented",
    "unselected_role",
    "undubbed",
    "dubbing_failed",
    "long_utterance",
    "duplicate_voice",
    "role_without_voice",
    "needs_human_review",
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_project_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    if not cleaned:
        raise ValueError("project_id 不能为空")
    return cleaned[:80]


def new_project_id() -> str:
    return f"project-{uuid.uuid4().hex[:12]}"


def project_output_roots(data_root: Path, project_id: str) -> dict[str, str]:
    safe_id = safe_project_id(project_id)
    output_root = data_root / "outputs" / safe_id
    return {
        "audio": str(output_root / "audio"),
        "exports": str(output_root / "exports"),
    }


def default_project(data_root: Path) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "project_id": DEFAULT_PROJECT_ID,
        "name": "默认项目",
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "output_roots": project_output_roots(data_root, DEFAULT_PROJECT_ID),
    }


def project_from_payload(payload: dict[str, Any], data_root: Path) -> dict[str, Any]:
    now = utc_now_iso()
    project_id = safe_project_id(str(payload.get("project_id") or new_project_id()))
    name = str(payload.get("name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_id": project_id,
        "name": name,
        "status": "active",
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
        "output_roots": project_output_roots(data_root, project_id),
    }


def with_output_roots(project: dict[str, Any], data_root: Path) -> dict[str, Any]:
    project_id = safe_project_id(str(project.get("project_id") or DEFAULT_PROJECT_ID))
    public_project = {
        key: value for key, value in project.items() if key != "workspace_state"
    }
    return {
        **public_project,
        "project_id": project_id,
        "output_roots": project_output_roots(data_root, project_id),
    }


def project_workspace_state_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw_state: Any = (payload or {}).get("workspace_state", payload or {})
    if not isinstance(raw_state, dict):
        raise ValueError("workspace_state 必须是对象")
    state = dict(raw_state)
    state.setdefault("schema_version", "v0.7.1")
    state["updated_at"] = utc_now_iso()
    return state


def build_quality_report(
    *,
    project_id: str,
    chapters: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    max_utterance_chars: int = DEFAULT_LONG_UTTERANCE_CHARS,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    paragraph_chapters: dict[str, dict[str, str]] = {}
    for chapter in chapters:
        chapter_id = str(chapter.get("chapter_id") or chapter.get("chapterId") or "")
        chapter_title = str(chapter.get("title") or chapter_id)
        for paragraph in chapter.get("paragraphs") or []:
            if not isinstance(paragraph, dict):
                continue
            paragraph_id = str(paragraph.get("paragraph_id") or paragraph.get("paragraphId") or "")
            if paragraph_id:
                paragraph_chapters[paragraph_id] = {
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                }

    for paragraph_id, chapter_meta in paragraph_chapters.items():
        if not utterances_by_paragraph.get(paragraph_id):
            issues.append(
                _issue(
                    project_id=project_id,
                    issue_type="unsegmented",
                    severity="blocking",
                    chapter_id=chapter_meta["chapter_id"],
                    paragraph_id=paragraph_id,
                    message="段落尚未划分台词。",
                )
            )

    for paragraph_id, utterances in utterances_by_paragraph.items():
        chapter_meta = paragraph_chapters.get(
            paragraph_id, {"chapter_id": "", "chapter_title": ""}
        )
        for utterance in utterances:
            if not isinstance(utterance, dict):
                continue
            issues.extend(
                _utterance_issues(
                    project_id=project_id,
                    chapter_id=chapter_meta["chapter_id"],
                    paragraph_id=paragraph_id,
                    utterance=utterance,
                    max_utterance_chars=max_utterance_chars,
                )
            )

    issues.extend(_role_issues(project_id=project_id, roles=roles))
    summary = {issue_type: 0 for issue_type in QUALITY_ISSUE_TYPES}
    for issue in issues:
        issue_type = str(issue.get("issue_type") or "")
        if issue_type in summary:
            summary[issue_type] += 1
    return {
        "project_id": safe_project_id(project_id),
        "summary": summary,
        "issues": issues,
        "can_generate": summary["unsegmented"] == 0 and summary["unselected_role"] == 0,
        "can_export": not any(
            summary[key] > 0
            for key in (
                "unsegmented",
                "unselected_role",
                "undubbed",
                "dubbing_failed",
                "long_utterance",
                "duplicate_voice",
                "role_without_voice",
                "needs_human_review",
            )
        ),
    }


def build_review_queue(
    *,
    quality_report: dict[str, Any],
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    filters = filters or {}
    items = [
        {**issue, "actions": _review_actions(str(issue.get("issue_type") or ""))}
        for issue in quality_report.get("issues", [])
        if _is_review_issue(issue)
    ]
    issue_type = filters.get("issue_type")
    if issue_type:
        items = [item for item in items if item.get("issue_type") == issue_type]
    chapter_id = filters.get("chapter_id")
    if chapter_id:
        items = [item for item in items if item.get("chapter_id") == chapter_id]
    role_id = filters.get("role_id")
    if role_id:
        items = [item for item in items if item.get("role_id") == role_id]
    return {
        "project_id": quality_report.get("project_id") or DEFAULT_PROJECT_ID,
        "items": items,
        "total_count": len(items),
        "filters": filters,
    }


def _utterance_issues(
    *,
    project_id: str,
    chapter_id: str,
    paragraph_id: str,
    utterance: dict[str, Any],
    max_utterance_chars: int,
) -> list[dict[str, Any]]:
    utterance_id = str(utterance.get("utterance_id") or "")
    text = str(utterance.get("text") or "")
    role_id = str(utterance.get("speaker_role_id") or utterance.get("role_id") or "")
    issues: list[dict[str, Any]] = []
    if not role_id:
        issues.append(
            _issue(
                project_id=project_id,
                issue_type="unselected_role",
                severity="blocking",
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                utterance_id=utterance_id,
                message="台词尚未选择角色。",
            )
        )
    if _is_audio_failed(utterance):
        issues.append(
            _issue(
                project_id=project_id,
                issue_type="dubbing_failed",
                severity="blocking",
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                utterance_id=utterance_id,
                role_id=role_id,
                message=str(utterance.get("audio_error") or "配音生成失败。"),
            )
        )
    elif role_id and not _has_audio(utterance):
        issues.append(
            _issue(
                project_id=project_id,
                issue_type="undubbed",
                severity="blocking",
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                utterance_id=utterance_id,
                role_id=role_id,
                message="台词尚未生成配音。",
            )
        )
    if len(text) > max_utterance_chars:
        issues.append(
            _issue(
                project_id=project_id,
                issue_type="long_utterance",
                severity="review",
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                utterance_id=utterance_id,
                role_id=role_id,
                message=f"台词长度 {len(text)} 字，超过阈值 {max_utterance_chars} 字。",
            )
        )
    if bool(utterance.get("needs_human_review")):
        issues.append(
            _issue(
                project_id=project_id,
                issue_type="needs_human_review",
                severity="review",
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                utterance_id=utterance_id,
                role_id=role_id,
                message="台词需要人工复核。",
            )
        )
    return issues


def _role_issues(*, project_id: str, roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    voice_to_roles: dict[str, list[dict[str, Any]]] = {}
    for role in roles:
        role_id = str(role.get("role_id") or "")
        voice_id = str(role.get("voice_resource_id") or "").strip()
        if not voice_id:
            issues.append(
                _issue(
                    project_id=project_id,
                    issue_type="role_without_voice",
                    severity="blocking",
                    role_id=role_id,
                    message=f"角色 {role.get('name') or role_id} 尚未绑定音色。",
                )
            )
            continue
        voice_to_roles.setdefault(voice_id, []).append(role)
    for voice_id, owners in voice_to_roles.items():
        if len(owners) <= 1:
            continue
        for role in owners:
            role_id = str(role.get("role_id") or "")
            issues.append(
                _issue(
                    project_id=project_id,
                    issue_type="duplicate_voice",
                    severity="blocking",
                    role_id=role_id,
                    message=f"音色 {voice_id} 被多个角色复用。",
                )
            )
    return issues


def _issue(
    *,
    project_id: str,
    issue_type: str,
    severity: str,
    message: str,
    chapter_id: str = "",
    paragraph_id: str = "",
    utterance_id: str = "",
    role_id: str = "",
) -> dict[str, Any]:
    key_parts = [issue_type, chapter_id, paragraph_id, utterance_id, role_id]
    return {
        "issue_id": ":".join(part for part in key_parts if part),
        "project_id": safe_project_id(project_id),
        "issue_type": issue_type,
        "severity": severity,
        "chapter_id": chapter_id,
        "paragraph_id": paragraph_id,
        "utterance_id": utterance_id,
        "role_id": role_id,
        "message": message,
    }


def _has_audio(utterance: dict[str, Any]) -> bool:
    return bool(utterance.get("audio_url") or utterance.get("audio_path"))


def _is_audio_failed(utterance: dict[str, Any]) -> bool:
    return bool(utterance.get("audio_error")) or str(
        utterance.get("audio_status") or ""
    ).lower() == "failed"


def _is_review_issue(issue: dict[str, Any]) -> bool:
    return issue.get("issue_type") in {
        "needs_human_review",
        "unselected_role",
        "dubbing_failed",
        "long_utterance",
    }


def _review_actions(issue_type: str) -> list[str]:
    if issue_type == "dubbing_failed":
        return ["jump", "retry_dubbing"]
    if issue_type == "unselected_role":
        return ["jump", "change_role"]
    if issue_type == "long_utterance":
        return ["jump", "split_text", "confirm"]
    return ["jump", "confirm", "change_role"]
