from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_docs_index_links_new_plan_and_existing_acceptance_sources():
    """Covers AC-DOC-04 and AC-REAL-05 coverage traceability."""
    index = read("docs/index.md")

    required_links = [
        "docs/development/acceptance-standard.md",
        "docs/development/test-strategy.md",
        "docs/development/real-environment-testing.md",
        "docs/superpowers/plans/2026-07-29-v0-1-manual-collaboration.md",
    ]
    for link in required_links:
        assert link in index


def test_frontend_workbench_structure_matches_manual_collaboration_flow():
    """Covers AC-FLOW-01 through AC-FLOW-08 and AC-REAL-03 structural evidence."""
    app = read("frontend/src/App.tsx")
    styles = read("frontend/src/styles.css")
    package_json = read("frontend/package.json")
    vite_config = read("frontend/vite.config.ts")

    assert '"react"' in package_json
    assert '"vite"' in package_json
    assert "人工主导" in app
    assert "小说导入" in app
    assert 'type="file"' in app
    assert 'accept=".txt,text/plain"' in app
    assert "章节列表" in app
    assert "角色卡" in app
    assert "当前章节正文" in app
    assert "确认无误" in app
    assert "语句划分" in app
    assert "音频试听" in app
    assert 'fetch(path' in app
    assert '"/api/novels/parse"' in app
    assert "`/api/roles/${roleId}`" in app
    assert '}/segment`' in app
    assert '}/speech`' in app
    assert "<audio controls" in app
    assert '"/api": "http://127.0.0.1:8000"' in vite_config
    assert '"/outputs": "http://127.0.0.1:8000"' in vite_config

    for control in ["折叠", "展开", "删除", "textarea", "select", "emotion", "speed", "volume", "designPrompt"]:
        assert control in app

    assert "confirmed" in app
    assert "setConfirmed" in app
    assert "roleOptions" in app
    assert "25%" in styles or "1fr 3fr" in styles
    assert "75%" in styles or "1fr 3fr" in styles


def test_default_voice_samples_are_labeled_as_smoke_test_placeholders():
    """Covers AC-ROLE-05 and AC-AUDIO-08."""
    app = read("frontend/src/App.tsx")
    manifest = read("assets/samples/manifest.json")

    assert "功能烟测占位，不代表最终音色质量" in app
    assert "narrator-male-female-smoke-test-placeholder" in manifest


def test_verification_document_records_real_environment_evidence_requirements():
    """Covers AC-REAL-01, AC-REAL-02, AC-REAL-03, AC-REAL-04."""
    verification = read("docs/development/v0.1-verification.md")

    required_evidence_terms = [
        "SiliconFlow",
        "Qwen3-TTS",
        "UI 截图",
        "ffprobe",
        "真实环境",
        "mock 只能用于单元测试",
    ]
    for term in required_evidence_terms:
        assert term in verification
