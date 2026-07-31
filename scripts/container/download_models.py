#!/usr/bin/env python3
"""Download configured Hugging Face models once and reuse the durable model volume."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

MARKER_NAME = ".novelvoice-model.json"


@dataclass(frozen=True)
class ModelSpec:
    repo_id: str
    revision: str | None
    target: Path


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _enabled(value: str) -> bool:
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _has_payload(directory: Path) -> bool:
    return directory.is_dir() and any(path.name != MARKER_NAME for path in directory.iterdir())


def _write_marker(target: Path, spec: ModelSpec, status: str) -> None:
    marker = {
        "repo_id": spec.repo_id,
        "revision": spec.revision,
        "status": status,
    }
    (target / MARKER_NAME).write_text(
        json.dumps(marker, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )


def _completed_cache(target: Path, spec: ModelSpec) -> bool:
    marker_path = target / MARKER_NAME
    if not _has_payload(target) or not marker_path.is_file():
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return marker.get("repo_id") == spec.repo_id and marker.get("revision") == spec.revision


def ensure_model(spec: ModelSpec) -> str:
    if _completed_cache(spec.target, spec):
        print(f"model cache hit: {spec.repo_id} -> {spec.target}", flush=True)
        return "cached"

    if (spec.target / MARKER_NAME).is_file():
        raise RuntimeError(
            f"model cache metadata does not match requested model; preserving {spec.target}"
        )

    if _has_payload(spec.target):
        _write_marker(spec.target, spec, "preloaded")
        print(f"preserving preloaded model: {spec.repo_id} -> {spec.target}", flush=True)
        return "preloaded"

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for automatic model download") from exc

    partial = spec.target.parent / f".{spec.target.name}.partial"
    partial.mkdir(parents=True, exist_ok=True)
    print(f"downloading model: {spec.repo_id} -> {spec.target}", flush=True)
    kwargs = {
        "repo_id": spec.repo_id,
        "revision": spec.revision,
        "local_dir": str(partial),
    }
    snapshot_download(**kwargs)
    if not _has_payload(partial):
        raise RuntimeError(f"download completed without model files: {spec.repo_id}")
    _write_marker(partial, spec, "downloaded")
    if spec.target.exists():
        if any(spec.target.iterdir()):
            raise RuntimeError(f"refusing to replace non-empty model directory: {spec.target}")
        spec.target.rmdir()
    partial.replace(spec.target)
    return "downloaded"


def configured_models(model_root: Path) -> list[ModelSpec]:
    base_id = _env(
        "NOVELVOICE_TTS_MODEL_ID",
        "SHUYI_TTS_MODEL_ID",
        default="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    )
    design_id = _env(
        "NOVELVOICE_TTS_VOICE_DESIGN_MODEL_ID",
        "SHUYI_TTS_VOICE_DESIGN_MODEL_ID",
        default="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    )
    revision = _env("NOVELVOICE_MODEL_REVISION", "SHUYI_MODEL_REVISION") or None
    return [
        ModelSpec(base_id, revision, model_root / base_id.rsplit("/", 1)[-1]),
        ModelSpec(design_id, revision, model_root / design_id.rsplit("/", 1)[-1]),
    ]


def main() -> int:
    auto_download = _env(
        "NOVELVOICE_MODEL_AUTO_DOWNLOAD",
        "SHUYI_MODEL_AUTO_DOWNLOAD",
        default="1",
    )
    if not _enabled(auto_download):
        print("automatic model download disabled", flush=True)
        return 0

    model_root = Path(
        _env("NOVELVOICE_MODEL_DIR", "SHUYI_MODEL_DIR", default="/models")
    ).expanduser()
    model_root.mkdir(parents=True, exist_ok=True)
    for spec in configured_models(model_root):
        ensure_model(spec)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"model download failed: {exc}", file=__import__("sys").stderr, flush=True)
        raise SystemExit(1) from exc
