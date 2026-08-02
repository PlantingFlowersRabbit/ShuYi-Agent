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
def test_v0_5_compose_selects_runtime_and_persists_manual_models(
    compose_file: str, target: str, device: str
):
    """Covers v0.5 CPU/CUDA compose selection and durable manual model deployment."""
    service = _app_service(_compose_config(compose_file))

    assert service["build"]["target"] == target
    environment = service["environment"]
    assert environment["SHUYI_DEVICE"] == device
    compose_text = (ROOT / compose_file).read_text(encoding="utf-8")
    assert 'SHUYI_MODEL_AUTO_DOWNLOAD: "${SHUYI_MODEL_AUTO_DOWNLOAD:-0}"' in compose_text
    assert environment["SHUYI_MODEL_DIR"] == "/models"
    assert any(volume.get("target") == "/models" for volume in service["volumes"])
    assert _duration_seconds(service["healthcheck"]["start_period"]) >= 300


@pytest.mark.parametrize("compose_file", ["compose.cpu.yaml", "compose.cuda.yaml"])
def test_v0_5_compose_accepts_public_host_port_without_api_token(compose_file: str):
    service = _app_service(_compose_config(compose_file))

    _ = service["environment"]
    assert "SHUYI_API_TOKEN" not in (ROOT / compose_file).read_text(encoding="utf-8")
    assert any(
        port.get("host_ip") == "0.0.0.0"
        and port.get("target") == 8000
        and port.get("published") == "8000"
        for port in service["ports"]
    )
    assert "0.0.0.0:${SHUYI_HOST_PORT:-8000}:8000" in (ROOT / compose_file).read_text(encoding="utf-8")


def test_v0_5_dockerfile_defines_cpu_and_cuda_runtime_targets():
    """Covers v0.5 build contract without requiring an image build in unit tests."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    targets = set(
        re.findall(
            r"^FROM\s+\S+(?:\s+AS\s+([\w.-]+))?\s*$", dockerfile, flags=re.MULTILINE | re.IGNORECASE
        )
    )
    assert {"cpu-runtime", "cuda-runtime"}.issubset(targets)


def test_v0_5_cnb_pipeline_has_cpu_gpu_build_and_versioned_publish_contracts():
    pipeline = (ROOT / ".cnb.yml").read_text(encoding="utf-8")

    for required in [
        "cpu-test",
        "gpu-real-inference",
        "--gpus all",
        "--target cpu-runtime",
        "--target cuda-runtime",
        "v0.5.2-cpu",
        "CNB_TAG:-}",
        "v0.5.2-cuda",
        "CNB_COMMIT_SHA",
    ]:
        assert required in pipeline


def test_v0_5_cnb_workspace_launch_button_starts_shuyi_agent():
    settings = (ROOT / ".cnb/settings.yml").read_text(encoding="utf-8")
    cnb_config = (ROOT / ".cnb.yml").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts/cnb/start-shuyi-agent.sh").read_text(encoding="utf-8")

    assert "启动 ShuYi-Agent" in settings
    assert "CNB_WELCOME_CMD" in cnb_config
    assert "bash scripts/cnb/start-shuyi-agent.sh" in cnb_config
    vscode_settings = (ROOT / ".vscode/settings.json").read_text(encoding="utf-8")

    assert "SHUYI_HOST_PORT:=8000" in launcher
    assert "docker compose -f compose.cuda.yaml down --remove-orphans" in launcher
    assert "CNB_VSCODE_PROXY_URI" in launcher
    assert "后端公网访问地址" in launcher
    assert "remote.autoForwardPorts" in vscode_settings
    assert "8000" in vscode_settings
    assert ".shuyi-api-token" not in launcher
    assert "Authorization: Bearer" not in launcher
    assert "docker compose -f compose.cuda.yaml up --build" in launcher
