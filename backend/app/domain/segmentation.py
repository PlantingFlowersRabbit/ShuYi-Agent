from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

REQUIRED_UTTERANCE_FIELDS = {
    "utterance_id",
    "speaker_name",
    "speaker_role_id",
    "voice_mode",
    "text",
    "emotion",
    "speed",
    "volume",
    "design_prompt",
    "confidence",
    "needs_human_review",
}
VOICE_MODES = {"voice_cloning", "voice_design"}


@dataclass
class SegmentationValidationResult:
    ok: bool
    paragraph_id: str
    utterances: list[dict[str, Any]] = field(default_factory=list)
    raw_output: str | None = None
    error_code: str | None = None
    error: str | None = None
    repaired: bool = False


def normalize_text_for_conservation(text: str) -> str:
    normalized = text
    replacements = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
        "—": "-",
        "－": "-",
        "–": "-",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return re.sub(r"\s+", "", normalized)


def _parse_json_once(raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(parsed, dict):
        return None, "Model output must be a JSON object"
    return parsed, None


def repair_json_output_once(raw_output: str) -> str:
    candidate = raw_output.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?", "", candidate, flags=re.IGNORECASE).strip()
        candidate = re.sub(r"```$", "", candidate).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        return candidate[start : end + 1]
    return candidate


def _known_role_maps(known_roles: list[dict[str, Any]]) -> tuple[set[str], dict[str, str]]:
    ids = {role["role_id"] for role in known_roles if role.get("role_id")}
    names = {role["name"]: role["role_id"] for role in known_roles if role.get("name") and role.get("role_id")}
    return ids, names


def _validate_utterance_schema(utterance: dict[str, Any]) -> str | None:
    missing = REQUIRED_UTTERANCE_FIELDS - set(utterance)
    if missing:
        return f"missing fields: {sorted(missing)}"
    if utterance["voice_mode"] not in VOICE_MODES:
        return "invalid voice_mode"
    if not isinstance(utterance["text"], str) or not utterance["text"]:
        return "text must be non-empty string"
    if not isinstance(utterance["needs_human_review"], bool):
        return "needs_human_review must be boolean"
    for key in ("speed", "volume", "confidence"):
        if not isinstance(utterance[key], int | float):
            return f"{key} must be numeric"
    if not 0 <= float(utterance["confidence"]) <= 1:
        return "confidence out of range"
    if not 0.5 <= float(utterance["speed"]) <= 2.0:
        return "speed out of range"
    if not 0.0 <= float(utterance["volume"]) <= 2.0:
        return "volume out of range"
    if utterance["voice_mode"] == "voice_design" and not utterance.get("design_prompt"):
        return "voice_design requires design_prompt"
    return None


def validate_segmentation_result(
    *,
    paragraph_id: str,
    paragraph_text: str,
    raw_output: str,
    known_roles: list[dict[str, Any]],
    repair_json: Callable[[str], str] | None = None,
) -> SegmentationValidationResult:
    parsed, error = _parse_json_once(raw_output)
    repaired = False
    if parsed is None and repair_json is not None:
        repaired = True
        repaired_output = repair_json(raw_output)
        parsed, error = _parse_json_once(repaired_output)
    if parsed is None:
        return SegmentationValidationResult(
            ok=False,
            paragraph_id=paragraph_id,
            raw_output=raw_output,
            error_code="invalid_json",
            error=error,
            repaired=repaired,
        )

    if parsed.get("paragraph_id") != paragraph_id:
        return SegmentationValidationResult(
            ok=False,
            paragraph_id=paragraph_id,
            raw_output=raw_output,
            error_code="paragraph_id_mismatch",
            error="paragraph_id does not match request",
            repaired=repaired,
        )

    utterances = parsed.get("utterances")
    if not isinstance(utterances, list) or not utterances:
        return SegmentationValidationResult(
            ok=False,
            paragraph_id=paragraph_id,
            raw_output=raw_output,
            error_code="invalid_schema",
            error="utterances must be a non-empty list",
            repaired=repaired,
        )

    known_ids, known_names = _known_role_maps(known_roles)
    normalized_utterances: list[dict[str, Any]] = []
    for utterance in utterances:
        if not isinstance(utterance, dict):
            return SegmentationValidationResult(
                ok=False,
                paragraph_id=paragraph_id,
                raw_output=raw_output,
                error_code="invalid_schema",
                error="utterance must be object",
                repaired=repaired,
            )
        schema_error = _validate_utterance_schema(utterance)
        if schema_error:
            return SegmentationValidationResult(
                ok=False,
                paragraph_id=paragraph_id,
                raw_output=raw_output,
                error_code="invalid_schema",
                error=schema_error,
                repaired=repaired,
            )

        item = dict(utterance)
        role_id = item.get("speaker_role_id")
        if role_id not in known_ids:
            matched_id = known_names.get(str(item.get("speaker_name", "")))
            if matched_id:
                item["speaker_role_id"] = matched_id
            else:
                item["speaker_role_id"] = None
                item["needs_human_review"] = True
        normalized_utterances.append(item)

    original = normalize_text_for_conservation(paragraph_text)
    generated = normalize_text_for_conservation("".join(item["text"] for item in normalized_utterances))
    if original != generated:
        return SegmentationValidationResult(
            ok=False,
            paragraph_id=paragraph_id,
            utterances=normalized_utterances,
            raw_output=raw_output,
            error_code="text_conservation_failed",
            error="utterance text does not conserve source paragraph",
            repaired=repaired,
        )

    return SegmentationValidationResult(
        ok=True,
        paragraph_id=paragraph_id,
        utterances=normalized_utterances,
        raw_output=raw_output,
        repaired=repaired,
    )
