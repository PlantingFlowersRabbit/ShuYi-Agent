from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _compose_config(filename: str) -> dict:
    completed = subprocess.run(
        ["docker", "compose", "-f", filename, "config", "--format", "json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _app_service(config: dict) -> dict:
    services = config.get("services", {})
    assert len(services) == 1, "each runtime compose file must define one deployable app service"
    return next(iter(services.values()))


def _duration_seconds(value: str) -> int:
    parts = re.fullmatch(r"(?:(\d+)m)?(?:(\d+)s)?", value)
    assert parts is not None, f"unsupported Compose duration: {value}"
    return int(parts.group(1) or 0) * 60 + int(parts.group(2) or 0)


@pytest.mark.parametrize(
    ("compose_file", "target", "device"),
    [
        ("compose.cpu.yaml", "cpu-runtime", "cpu"),
        ("compose.cuda.yaml", "cuda-runtime", "cuda"),
    ],
)
def test_v0_4_compose_selects_runtime_and_persists_first_start_models(
    compose_file: str, target: str, device: str
):
    """Covers v0.4 CPU/CUDA compose selection and durable first-start model downloads."""
    service = _app_service(_compose_config(compose_file))

    assert service["build"]["target"] == target
    environment = service["environment"]
    assert environment["NOVELVOICE_DEVICE"] == device
    assert environment["NOVELVOICE_MODEL_AUTO_DOWNLOAD"] == "1"
    assert environment["NOVELVOICE_MODEL_DIR"] == "/models"
    assert any(volume.get("target") == "/models" for volume in service["volumes"])
    assert _duration_seconds(service["healthcheck"]["start_period"]) >= 300


def test_v0_4_dockerfile_defines_cpu_and_cuda_runtime_targets():
    """Covers v0.4 build contract without requiring an image build in unit tests."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    targets = set(
        re.findall(
            r"^FROM\s+\S+(?:\s+AS\s+([\w.-]+))?\s*$", dockerfile, flags=re.MULTILINE | re.IGNORECASE
        )
    )
    assert {"cpu-runtime", "cuda-runtime"}.issubset(targets)
