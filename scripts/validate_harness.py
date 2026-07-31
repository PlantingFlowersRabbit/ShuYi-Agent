#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FILES = [
    "AGENTS.md",
    "AGENT.md",
    "README.md",
    "pyproject.toml",
    ".env.example",
    ".gitignore",
    "spec/v0.1-manual-collaboration.md",
    "spec/v0.11-harness.md",
    "spec/v0.12-harness.md",
    "spec/v0.13-harness.md",
    "spec/v0.20-harness.md",
    "spec/v0.22-harness.md",
    "spec/v0.23-harness.md",
    "spec/v0.24-harness.md",
    "spec/v0.25-harness.md",
    "spec/v0.251-harness.md",
    "spec/v0.30-harness.md",
    "spec/v0.31-harness.md",
    "spec/product-scope.md",
    "spec/architecture-contract.md",
    "spec/llm-segmentation-contract.md",
    "spec/audio-synthesis-contract.md",
    "assets/README.md",
    "assets/READEME.md",
    "assets/samples/manifest.json",
    "assets/samples/LICENSES.md",
    "docs/index.md",
    "docs/harness-principles.md",
    "docs/subagent-guide.md",
    "docs/builder-reviewer-separation.md",
    "docs/development/acceptance-standard.md",
    "docs/development/test-strategy.md",
    "docs/development/real-environment-testing.md",
    "docs/development/v0.11-verification.md",
    "docs/development/v0.12-verification.md",
    "docs/development/v0.13-verification.md",
    "docs/development/v0.20-verification.md",
    "docs/development/v0.22-verification.md",
    "docs/development/v0.23-verification.md",
    "docs/development/v0.24-verification.md",
    "docs/development/v0.25-verification.md",
    "docs/development/v0.251-verification.md",
    "docs/development/v0.30-verification.md",
    "docs/development/v0.31-verification.md",
    "docs/experience-library/README.md",
    "docs/experience-library/active-rules.md",
    "docs/experience-library/lessons.md",
    ".codex/agents/builder.toml",
    ".codex/agents/test-author.toml",
    ".codex/agents/acceptance-checker.toml",
    ".codex/agents/visual-reviewer.toml",
    ".codex/agents/audio-reviewer.toml",
    ".codex/agents/reviewer.toml",
    "backend/tts/qwen3_tts_server.py",
    "backend/tts/README.md",
    "models/README.md",
    "outputs/README.md",
]


REQUIRED_DOC_LINKS = [
    "docs/harness-principles.md",
    "docs/subagent-guide.md",
    "docs/builder-reviewer-separation.md",
    "docs/development/acceptance-standard.md",
    "docs/development/test-strategy.md",
    "docs/development/real-environment-testing.md",
    "docs/development/v0.11-verification.md",
    "docs/development/v0.12-verification.md",
    "docs/development/v0.13-verification.md",
    "docs/development/v0.20-verification.md",
    "docs/development/v0.22-verification.md",
    "docs/development/v0.23-verification.md",
    "docs/development/v0.24-verification.md",
    "docs/development/v0.25-verification.md",
    "docs/development/v0.251-verification.md",
    "docs/development/v0.30-verification.md",
    "docs/development/v0.31-verification.md",
    "docs/experience-library/README.md",
    "docs/experience-library/active-rules.md",
    "docs/experience-library/lessons.md",
]


MANIFEST_REQUIRED_FIELDS = {
    "source_url",
    "license",
    "source_project",
    "original_filename",
    "clip_range_seconds",
    "transcript",
    "intended_role",
    "can_redistribute",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def check_required_files() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        fail("Missing required files:\n" + "\n".join(missing))


def check_docs_index() -> None:
    index = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    missing = [path for path in REQUIRED_DOC_LINKS if path not in index]
    if missing:
        fail("docs/index.md missing links:\n" + "\n".join(missing))


def check_manifest() -> None:
    manifest_path = ROOT / "assets/samples/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resources = manifest.get("resources", [])
    if not resources:
        fail("manifest has no resources")

    for resource in resources:
        resource_id = resource.get("id", "<missing id>")
        missing = sorted(MANIFEST_REQUIRED_FIELDS - set(resource))
        if missing:
            fail(f"{resource_id} missing fields: {missing}")

        local_path = resource.get("local_path")
        if local_path and not (ROOT / local_path).exists():
            fail(f"{resource_id} local_path does not exist: {local_path}")

        transcript_path = resource.get("transcript_path")
        if transcript_path and not (ROOT / transcript_path).exists():
            fail(f"{resource_id} transcript_path does not exist: {transcript_path}")

        if "common-voice" in resource_id.lower():
            fail("Common Voice resources must not be committed as local samples")


def check_audio_decode() -> None:
    manifest = json.loads((ROOT / "assets/samples/manifest.json").read_text(encoding="utf-8"))
    audio_paths = [
        resource["local_path"]
        for resource in manifest.get("resources", [])
        if resource.get("type") == "voice_reference"
    ]
    if not audio_paths:
        fail("manifest has no voice_reference resources")

    for audio_path in audio_paths:
        full_path = ROOT / audio_path
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(full_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            fail(f"ffprobe failed for {audio_path}: {result.stderr.strip()}")
        try:
            duration = float(result.stdout.strip())
        except ValueError:
            fail(f"ffprobe returned non-numeric duration for {audio_path}: {result.stdout!r}")
        if duration <= 0:
            fail(f"audio duration must be > 0 for {audio_path}")


def main() -> None:
    check_required_files()
    check_docs_index()
    check_manifest()
    check_audio_decode()
    print("OK: harness files, docs index, manifest, and audio decode checks passed")


if __name__ == "__main__":
    main()
