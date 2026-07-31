from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from scripts.container.download_models import ModelSpec, ensure_model

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADER = ROOT / "scripts/container/download_models.py"


def _run_downloader(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_package = tmp_path / "fake_packages" / "huggingface_hub"
    fake_package.mkdir(parents=True)
    (fake_package / "__init__.py").write_text(
        textwrap.dedent(
            """
            import json
            import os
            from pathlib import Path

            def snapshot_download(repo_id, local_dir, revision=None, **kwargs):
                log = Path(os.environ["FAKE_HF_LOG"])
                with log.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"repo_id": repo_id, "revision": revision}) + "\\n")
                target = Path(local_dir)
                target.mkdir(parents=True, exist_ok=True)
                (target / "config.json").write_text("{}", encoding="utf-8")
                return str(target)
            """
        ),
        encoding="utf-8",
    )
    model_dir = tmp_path / "models"
    log_path = tmp_path / "downloads.log"
    env = os.environ | {
        "PYTHONPATH": str(fake_package.parent),
        "FAKE_HF_LOG": str(log_path),
        "NOVELVOICE_MODEL_DIR": str(model_dir),
        "NOVELVOICE_TTS_MODEL_ID": "test/base",
        "NOVELVOICE_TTS_VOICE_DESIGN_MODEL_ID": "test/design",
        "NOVELVOICE_MODEL_AUTO_DOWNLOAD": "1",
    }
    first = subprocess.run(
        ["python3", str(DOWNLOADER)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        ["python3", str(DOWNLOADER)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    return second, log_path


def test_model_downloader_reuses_completed_cache_without_second_download(tmp_path: Path):
    _run_downloader(tmp_path)

    log_lines = (tmp_path / "downloads.log").read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 2
    assert {json.loads(line)["repo_id"] for line in log_lines} == {"test/base", "test/design"}
    for model_name in ("base", "design"):
        marker = tmp_path / "models" / model_name / ".novelvoice-model.json"
        assert json.loads(marker.read_text(encoding="utf-8"))["status"] == "downloaded"


def test_model_downloader_preserves_cache_when_metadata_conflicts(tmp_path: Path):
    target = tmp_path / "models" / "base"
    target.mkdir(parents=True)
    (target / "config.json").write_text("{}", encoding="utf-8")
    marker = target / ".novelvoice-model.json"
    original_marker = '{"repo_id":"old/base","revision":null,"status":"downloaded"}'
    marker.write_text(original_marker, encoding="utf-8")

    with pytest.raises(RuntimeError, match="metadata does not match"):
        ensure_model(ModelSpec("new/base", None, target))

    assert marker.read_text(encoding="utf-8") == original_marker
