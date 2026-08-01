from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v0_4_package_names_use_shuyi_agent_brand():
    """Covers v0.4 package branding at Python and frontend boundaries."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))

    assert project["project"]["name"] == "shuyi-agent"
    assert frontend["name"] == "shuyi-agent-frontend"


def test_v0_4_package_versions_are_consistent():
    """Covers v0.4 release version at Python and frontend boundaries."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))

    assert project["project"]["version"] == "0.4.2"
    assert frontend["version"] == "0.4.2"


def test_v0_4_harness_prompt_is_ignored():
    """Covers v0.4 repository hygiene for runtime prompt material."""
    ignored = subprocess.run(
        ["git", "check-ignore", "harness_prompt/example.md"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0, "harness_prompt/ must be ignored"


def test_v0_4_legacy_development_agents_are_untracked():
    """Covers v0.4 removal of retired development-only agent files."""
    tracked_agents = subprocess.run(
        ["git", "ls-files", ".codex/agents"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert tracked_agents == [], ".codex/agents contains retired development-only agent files"
