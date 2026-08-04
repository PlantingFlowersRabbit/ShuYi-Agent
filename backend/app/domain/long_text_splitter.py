from __future__ import annotations

import copy
import re
from typing import Any

DEFAULT_MAX_UTTERANCE_CHARS = 120


def detect_long_utterances(
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    *,
    max_chars: int = DEFAULT_MAX_UTTERANCE_CHARS,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for paragraph_id, utterances in utterances_by_paragraph.items():
        for utterance in utterances:
            text = str(utterance.get("text") or "")
            if len(text) <= max_chars:
                continue
            items.append(
                {
                    "paragraph_id": str(utterance.get("paragraph_id") or paragraph_id),
                    "utterance_id": str(utterance.get("utterance_id") or ""),
                    "char_count": len(text),
                    "max_chars": max_chars,
                    "text": text,
                    "speaker_role_id": utterance.get("speaker_role_id") or utterance.get("role_id"),
                }
            )
    return items


def split_long_utterance_groups(
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    *,
    utterance_id: str,
    max_chars: int = DEFAULT_MAX_UTTERANCE_CHARS,
) -> dict[str, Any]:
    groups = _clone_groups(utterances_by_paragraph)
    paragraph_id, index, source = _find_utterance(groups, utterance_id)
    original_text = str(source.get("text") or "")
    segments = split_text_for_tts(original_text, max_chars=max_chars)
    if len(segments) <= 1:
        replacement = [_reset_for_retry({**source, "text": original_text})]
    else:
        replacement = [
            _reset_for_retry(
                {
                    **source,
                    "utterance_id": utterance_id if offset == 1 else f"{utterance_id}-s{offset:03d}",
                    "text": segment,
                    "source_utterance_id": utterance_id,
                    "split_index": offset,
                    "split_count": len(segments),
                }
            )
            for offset, segment in enumerate(segments, start=1)
        ]
    groups[paragraph_id][index : index + 1] = replacement
    return {
        "utterances_by_paragraph": groups,
        "split_report": {
            "source_utterance_id": utterance_id,
            "paragraph_id": paragraph_id,
            "strategy": "punctuation_then_window",
            "segment_count": len(replacement),
            "max_chars": max_chars,
            "text_conservation": text_conservation_report(original_text, [item["text"] for item in replacement]),
        },
    }


def merge_utterance_groups(
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    *,
    paragraph_id: str,
    utterance_ids: list[str],
) -> dict[str, Any]:
    groups = _clone_groups(utterances_by_paragraph)
    if paragraph_id not in groups:
        raise ValueError("paragraph_id 不存在")
    ids = [str(item) for item in utterance_ids if str(item).strip()]
    if not ids:
        raise ValueError("utterance_ids 不能为空")
    id_set = set(ids)
    utterances = groups[paragraph_id]
    selected = [(index, item) for index, item in enumerate(utterances) if item.get("utterance_id") in id_set]
    if len(selected) != len(ids):
        raise ValueError("待合并台词不存在")
    indexes = [index for index, _item in selected]
    if indexes != list(range(min(indexes), max(indexes) + 1)):
        raise ValueError("只能合并同一段内连续台词")
    first = copy.deepcopy(selected[0][1])
    original_texts = [str(item.get("text") or "") for _index, item in selected]
    merged_text = "".join(original_texts)
    merged = _reset_for_retry(
        {
            **first,
            "text": merged_text,
            "merged_utterance_ids": ids,
            "split_index": None,
            "split_count": None,
        }
    )
    start = indexes[0]
    groups[paragraph_id][start : indexes[-1] + 1] = [merged]
    return {
        "utterances_by_paragraph": groups,
        "merge_report": {
            "paragraph_id": paragraph_id,
            "merged_utterance_ids": ids,
            "target_utterance_id": merged["utterance_id"],
            "text_conservation": text_conservation_report(merged_text, [merged["text"]]),
        },
    }


def bulk_update_role(
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    *,
    utterance_ids: list[str],
    role_id: str,
    speaker_name: str,
) -> dict[str, Any]:
    groups = _clone_groups(utterances_by_paragraph)
    id_set = {str(item) for item in utterance_ids if str(item).strip()}
    updated_count = 0
    for utterances in groups.values():
        for utterance in utterances:
            if utterance.get("utterance_id") not in id_set:
                continue
            utterance["speaker_role_id"] = role_id
            utterance["role_id"] = role_id
            utterance["speaker_name"] = speaker_name
            utterance["needs_human_review"] = False
            updated_count += 1
    return {"utterances_by_paragraph": groups, "updated_count": updated_count}


def prepare_retry_queue(
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    *,
    utterance_ids: list[str] | None = None,
) -> dict[str, Any]:
    groups = _clone_groups(utterances_by_paragraph)
    id_set = {str(item) for item in utterance_ids or [] if str(item).strip()}
    retry_items: list[dict[str, str]] = []
    for paragraph_id, utterances in groups.items():
        for utterance in utterances:
            if id_set and utterance.get("utterance_id") not in id_set:
                continue
            if not id_set and not _is_failed(utterance):
                continue
            _reset_for_retry(utterance)
            retry_items.append(
                {
                    "paragraph_id": str(utterance.get("paragraph_id") or paragraph_id),
                    "utterance_id": str(utterance.get("utterance_id") or ""),
                }
            )
    return {"utterances_by_paragraph": groups, "retry_items": retry_items}


def split_text_for_tts(text: str, *, max_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0")
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    parts = re.findall(r".+?[。！？!?；;，,、]|.+$", text)
    segments: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                segments.append(current)
                current = ""
            segments.extend(part[index : index + max_chars] for index in range(0, len(part), max_chars))
            continue
        if current and len(current) + len(part) > max_chars:
            segments.append(current)
            current = part
        else:
            current += part
    if current:
        segments.append(current)
    return segments


def text_conservation_report(original: str, segments: list[str]) -> dict[str, Any]:
    joined = "".join(segments)
    return {
        "matches": joined == original,
        "original_length": len(original),
        "joined_length": len(joined),
        "segment_count": len(segments),
    }


def _clone_groups(
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        str(paragraph_id): [copy.deepcopy(item) for item in utterances if isinstance(item, dict)]
        for paragraph_id, utterances in utterances_by_paragraph.items()
        if isinstance(utterances, list)
    }


def _find_utterance(
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
    utterance_id: str,
) -> tuple[str, int, dict[str, Any]]:
    for paragraph_id, utterances in utterances_by_paragraph.items():
        for index, utterance in enumerate(utterances):
            if str(utterance.get("utterance_id") or "") == utterance_id:
                return paragraph_id, index, utterance
    raise ValueError("台词不存在")


def _reset_for_retry(utterance: dict[str, Any]) -> dict[str, Any]:
    utterance["audio_status"] = "pending_retry"
    utterance["audio_error"] = ""
    utterance.pop("audio_url", None)
    utterance.pop("audio_path", None)
    utterance.pop("audio_duration", None)
    utterance.pop("audio_provider", None)
    utterance.pop("audio_model", None)
    utterance["needs_human_review"] = True
    return utterance


def _is_failed(utterance: dict[str, Any]) -> bool:
    return bool(utterance.get("audio_error")) or str(utterance.get("audio_status") or "").lower() in {
        "failed",
        "音频生成失败",
    }
