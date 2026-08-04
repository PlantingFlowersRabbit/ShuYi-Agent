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


def test_v0_62_qdrant_compose_adds_local_vector_store():
    """v0.6.6 ships an optional Qdrant service for Story Bible RAG indexing."""
    compose_path = ROOT / "compose.qdrant.yaml"
    assert compose_path.exists()
    config = _compose_config("compose.qdrant.yaml")
    qdrant = config["services"]["qdrant"]

    assert qdrant["image"].startswith("qdrant/qdrant:")
    assert any(port.get("target") == 6333 for port in qdrant["ports"])
    assert any(volume.get("target") == "/qdrant/storage" for volume in qdrant["volumes"])
    assert "qdrant-data" in config["volumes"]


def test_v0_5_cnb_pipeline_has_cpu_gpu_build_and_versioned_publish_contracts():
    pipeline = (ROOT / ".cnb.yml").read_text(encoding="utf-8")

    for required in [
        "cpu-test",
        "gpu-real-inference",
        "--gpus all",
        "--target cpu-runtime",
        "--target cuda-runtime",
        "v0.6.6-cpu",
        "CNB_TAG:-}",
        "v0.6.6-cuda",
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
    devcontainer = json.loads((ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8"))

    assert "CNB_VSCODE_PROXY_URI" not in launcher
    assert "后端公网访问地址：" not in launcher
    assert "后端本地访问地址：http://localhost:${SHUYI_HOST_PORT}" in launcher
    assert "PORTS 面板显示的 Forwarded Address 为准" in launcher
    assert "remote.autoForwardPorts" in vscode_settings
    assert '"remote.autoForwardPortsSource": "output"' in vscode_settings
    assert "8000" in vscode_settings
    assert 8000 in devcontainer["forwardPorts"]
    assert devcontainer["portsAttributes"]["8000"]["label"] == "ShuYi-Agent 后端 API"
    assert ".shuyi-api-token" not in launcher
    assert "Authorization: Bearer" not in launcher
    assert "docker compose -f compose.cuda.yaml up --build" in launcher


def test_v0_5_cnb_launch_uses_public_browser_cors_without_workspace_whitelist():
    launcher = (ROOT / "scripts/cnb/start-shuyi-agent.sh").read_text(encoding="utf-8")
    compose_files = [
        (ROOT / "compose.cpu.yaml").read_text(encoding="utf-8"),
        (ROOT / "compose.cuda.yaml").read_text(encoding="utf-8"),
    ]

    assert "浏览器 CORS：公开 API 已统一允许跨域预检" in launcher
    assert "SHUYI_CORS_ORIGINS" not in launcher
    assert "SHUYI_CORS_ORIGIN_REGEX" not in launcher
    for compose_text in compose_files:
        assert "SHUYI_CORS_ORIGINS:" not in compose_text
        assert "SHUYI_CORS_ORIGIN_REGEX:" not in compose_text
