#!/usr/bin/env python3
"""按固定版本下载模型，并提供文件锁、校验和与下载源回退。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

MARKER_NAME = ".shuyi-model.json"
MARKER_SCHEMA_VERSION = 2
DEFAULT_REVISIONS = {
    "TTS": {
        "modelscope": "dfb4a462f62f8f831ff0ffabf31189fc9d4344fd",
        "huggingface": "fd4b254389122332181a7c3db7f27e918eec64e3",
    },
    "VOICE_DESIGN": {
        "modelscope": "8dd530dbed7fda907a15ac48d7f78742cc90a065",
        "huggingface": "5ecdb67327fd37bb2e042aab12ff7391903235d3",
    },
}


@dataclass(frozen=True)
class ModelSpec:
    modelscope_id: str
    huggingface_id: str
    modelscope_revision: str
    huggingface_revision: str
    target: Path


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _enabled(value: str) -> bool:
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _payload_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.rglob("*") if path.is_file() and path.name != MARKER_NAME),
        key=lambda path: path.relative_to(directory).as_posix(),
    )


def _directory_checksum(directory: Path) -> str:
    digest = hashlib.sha256()
    files = _payload_files(directory)
    if not files:
        raise RuntimeError(f"模型缓存中没有有效文件：{directory}")
    for path in files:
        relative = path.relative_to(directory).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _spec_identity(spec: ModelSpec) -> dict[str, str]:
    return {
        "modelscope_id": spec.modelscope_id,
        "huggingface_id": spec.huggingface_id,
        "modelscope_revision": spec.modelscope_revision,
        "huggingface_revision": spec.huggingface_revision,
    }


def _write_marker(target: Path, spec: ModelSpec, *, source: str, revision: str) -> None:
    marker = {
        "schema_version": MARKER_SCHEMA_VERSION,
        **_spec_identity(spec),
        "source": source,
        "revision": revision,
        "checksum": _directory_checksum(target),
        "status": "downloaded" if source != "preloaded" else "preloaded",
    }
    (target / MARKER_NAME).write_text(
        json.dumps(marker, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )


def _read_marker(target: Path) -> dict | None:
    marker_path = target / MARKER_NAME
    if not marker_path.is_file():
        return None
    try:
        value = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"模型缓存标记无效：{marker_path}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"模型缓存标记无效：{marker_path}")
    return value


def _verify_cache(target: Path, spec: ModelSpec, marker: dict) -> None:
    expected_identity = _spec_identity(spec)
    if any(marker.get(key) != value for key, value in expected_identity.items()):
        raise RuntimeError(f"模型缓存元数据不匹配，已保留原目录：{target}")
    expected_checksum = str(marker.get("checksum") or "")
    if not expected_checksum or _directory_checksum(target) != expected_checksum:
        raise RuntimeError(f"模型缓存校验和不匹配，已保留原目录：{target}")


@contextmanager
def _model_lock(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.parent / f".{target.name}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _download_modelscope(spec: ModelSpec, partial: Path) -> tuple[str, str, Path]:
    from modelscope import snapshot_download

    try:
        downloaded = snapshot_download(
            model_id=spec.modelscope_id,
            revision=spec.modelscope_revision,
            local_dir=str(partial),
        )
    except TypeError as exc:
        if "local_dir" not in str(exc):
            raise
        downloaded = snapshot_download(
            model_id=spec.modelscope_id,
            revision=spec.modelscope_revision,
            cache_dir=str(partial),
        )
    payload = Path(downloaded) if downloaded else partial
    return "modelscope", spec.modelscope_revision, payload


def _download_huggingface(spec: ModelSpec, partial: Path) -> tuple[str, str, Path]:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=spec.huggingface_id,
        revision=spec.huggingface_revision,
        local_dir=str(partial),
    )
    return "huggingface", spec.huggingface_revision, partial


def _fresh_partial(target: Path) -> Path:
    partial = target.parent / f".{target.name}.partial-{os.getpid()}-{uuid.uuid4().hex}"
    partial.mkdir(parents=True)
    return partial


def ensure_model(spec: ModelSpec) -> str:
    with _model_lock(spec.target):
        marker = _read_marker(spec.target)
        if marker is not None:
            _verify_cache(spec.target, spec, marker)
            print(f"命中模型缓存：{spec.target}", flush=True)
            return "cached"

        if _payload_files(spec.target):
            _write_marker(spec.target, spec, source="preloaded", revision="local")
            print(f"已校验并保留预置模型：{spec.target}", flush=True)
            return "preloaded"

        errors: list[str] = []
        for provider_name, downloader in (
            ("ModelScope", _download_modelscope),
            ("Hugging Face", _download_huggingface),
        ):
            partial = _fresh_partial(spec.target)
            try:
                print(f"正在从 {provider_name} 下载模型：{spec.target}", flush=True)
                source, revision, payload = downloader(spec, partial)
                if not payload.resolve().is_relative_to(partial.resolve()):
                    raise RuntimeError(f"下载源返回了暂存目录之外的模型路径：{payload}")
                _write_marker(payload, spec, source=source, revision=revision)
                if spec.target.exists():
                    if any(spec.target.iterdir()):
                        raise RuntimeError(f"拒绝替换非空模型目录：{spec.target}")
                    spec.target.rmdir()
                payload.replace(spec.target)
                shutil.rmtree(partial, ignore_errors=True)
                return "downloaded"
            except Exception as exc:  # noqa: BLE001 - 下载失败时记录错误并尝试备用来源。
                errors.append(f"{provider_name}: {exc}")
                shutil.rmtree(partial, ignore_errors=True)
        raise RuntimeError("所有模型下载源均失败：" + "；".join(errors))


def configured_models(model_root: Path) -> list[ModelSpec]:
    base_id = _env(
        "SHUYI_TTS_MODEL_ID",
        default="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    )
    design_id = _env(
        "SHUYI_TTS_VOICE_DESIGN_MODEL_ID",
        default="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    )

    def model_spec(model_id: str, kind: str) -> ModelSpec:
        modelscope_id = _env(
            f"SHUYI_MODELSCOPE_{kind}_MODEL_ID",
            default=model_id,
        )
        huggingface_id = _env(
            f"SHUYI_HUGGINGFACE_{kind}_MODEL_ID",
            default=model_id,
        )
        return ModelSpec(
            modelscope_id=modelscope_id,
            huggingface_id=huggingface_id,
            modelscope_revision=_env(
                f"SHUYI_MODELSCOPE_{kind}_REVISION",
                default=DEFAULT_REVISIONS[kind]["modelscope"],
            ),
            huggingface_revision=_env(
                f"SHUYI_HUGGINGFACE_{kind}_REVISION",
                default=DEFAULT_REVISIONS[kind]["huggingface"],
            ),
            target=model_root / modelscope_id.rsplit("/", 1)[-1],
        )

    return [model_spec(base_id, "TTS"), model_spec(design_id, "VOICE_DESIGN")]


def main() -> int:
    auto_download = _env(
        "SHUYI_MODEL_AUTO_DOWNLOAD",
        default="1",
    )
    if not _enabled(auto_download):
        print("已禁用自动模型下载", flush=True)
        return 0

    model_root = Path(_env("SHUYI_MODEL_DIR", default="/models")).expanduser()
    model_root.mkdir(parents=True, exist_ok=True)
    for spec in configured_models(model_root):
        ensure_model(spec)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TypeError) as exc:
        print(f"模型下载失败：{exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
