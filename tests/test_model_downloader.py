from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.container.download_models import ModelSpec, configured_models, ensure_model


def _spec(tmp_path: Path) -> ModelSpec:
    return ModelSpec(
        modelscope_id="test/base",
        huggingface_id="test/base",
        modelscope_revision="master",
        huggingface_revision="main",
        target=tmp_path / "models" / "base",
    )


def _write_model(local_dir: str, source: str) -> None:
    target = Path(local_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.json").write_text(json.dumps({"source": source}), encoding="utf-8")


def test_model_downloader_prefers_modelscope_and_reuses_verified_cache(tmp_path, monkeypatch):
    spec = _spec(tmp_path)
    calls: list[tuple[str, str, str]] = []

    def modelscope_download(model_id, revision, local_dir):
        calls.append(("modelscope", model_id, revision))
        assert not spec.target.exists()
        assert ".partial-" in Path(local_dir).name
        _write_model(local_dir, "modelscope")

    def forbidden_huggingface(**_kwargs):
        raise AssertionError("Hugging Face fallback should not run")

    monkeypatch.setitem(
        sys.modules, "modelscope", SimpleNamespace(snapshot_download=modelscope_download)
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=forbidden_huggingface),
    )

    assert ensure_model(spec) == "downloaded"
    assert ensure_model(spec) == "cached"
    assert calls == [("modelscope", "test/base", "master")]
    marker = json.loads((spec.target / ".shuyi-model.json").read_text(encoding="utf-8"))
    assert marker["source"] == "modelscope"
    assert marker["revision"] == "master"
    assert marker["checksum"]
    assert (spec.target.parent / ".base.lock").is_file()
    assert not list(spec.target.parent.glob(".base.partial-*"))


def test_model_downloader_falls_back_to_huggingface_after_modelscope_failure(tmp_path, monkeypatch):
    spec = _spec(tmp_path)
    calls: list[str] = []

    def failed_modelscope(model_id, revision, local_dir):
        calls.append("modelscope")
        _write_model(local_dir, "incomplete")
        raise RuntimeError("modelscope unavailable")

    def huggingface_download(repo_id, revision, local_dir):
        calls.append("huggingface")
        _write_model(local_dir, "huggingface")

    monkeypatch.setitem(
        sys.modules,
        "modelscope",
        SimpleNamespace(snapshot_download=failed_modelscope),
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=huggingface_download),
    )

    assert ensure_model(spec) == "downloaded"
    assert calls == ["modelscope", "huggingface"]
    marker = json.loads((spec.target / ".shuyi-model.json").read_text(encoding="utf-8"))
    assert marker["source"] == "huggingface"
    assert marker["revision"] == "main"
    assert json.loads((spec.target / "config.json").read_text(encoding="utf-8")) == {
        "source": "huggingface"
    }


def test_model_downloader_supports_modelscope_cache_dir_api(tmp_path, monkeypatch):
    spec = _spec(tmp_path)

    def modelscope_download(model_id, revision, cache_dir):
        downloaded = Path(cache_dir) / model_id
        _write_model(str(downloaded), "modelscope-cache-dir")
        return str(downloaded)

    def forbidden_huggingface(**_kwargs):
        raise AssertionError("compatible ModelScope SDK should not use fallback")

    monkeypatch.setitem(
        sys.modules, "modelscope", SimpleNamespace(snapshot_download=modelscope_download)
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=forbidden_huggingface),
    )

    assert ensure_model(spec) == "downloaded"
    assert json.loads((spec.target / "config.json").read_text(encoding="utf-8")) == {
        "source": "modelscope-cache-dir"
    }


def test_model_downloader_rejects_corrupted_cache_without_overwriting(tmp_path, monkeypatch):
    spec = _spec(tmp_path)
    calls = 0

    def modelscope_download(model_id, revision, local_dir):
        nonlocal calls
        calls += 1
        _write_model(local_dir, "modelscope")

    monkeypatch.setitem(
        sys.modules, "modelscope", SimpleNamespace(snapshot_download=modelscope_download)
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace())
    ensure_model(spec)
    config = spec.target / "config.json"
    config.write_text('{"source":"corrupted"}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="校验和"):
        ensure_model(spec)

    assert calls == 1
    assert config.read_text(encoding="utf-8") == '{"source":"corrupted"}'


def test_configured_models_have_fixed_nonempty_provider_revisions(tmp_path, monkeypatch):
    for kind in ("TTS", "VOICE_DESIGN"):
        monkeypatch.delenv(f"SHUYI_MODELSCOPE_{kind}_REVISION", raising=False)
        monkeypatch.delenv(f"SHUYI_HUGGINGFACE_{kind}_REVISION", raising=False)

    models = configured_models(tmp_path)

    assert models
    assert all(len(model.modelscope_revision) == 40 for model in models)
    assert all(len(model.huggingface_revision) == 40 for model in models)
    assert all(model.modelscope_revision not in {"main", "master"} for model in models)
    assert all(model.huggingface_revision not in {"main", "master"} for model in models)
