from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_docs_index_links_new_plan_and_existing_acceptance_sources():
    """Covers AC-DOC-04 and v0.11 coverage traceability."""
    index = read("docs/index.md")

    required_links = [
        "docs/development/acceptance-standard.md",
        "docs/development/test-strategy.md",
        "docs/development/real-environment-testing.md",
        "docs/superpowers/plans/2026-07-29-v0-1-manual-collaboration.md",
        "spec/v0.11-harness.md",
        "docs/development/v0.11-verification.md",
    ]
    for link in required_links:
        assert link in index


def test_frontend_workbench_structure_matches_v0_11_flow():
    """Covers v0.11 main page, voice library, model config, and nested utterance UI."""
    app = read("frontend/src/App.tsx")
    styles = read("frontend/src/styles.css")
    package_json = read("frontend/package.json")
    vite_config = read("frontend/vite.config.ts")

    assert '"react"' in package_json
    assert '"vite"' in package_json
    assert "NovelVoice-Agent v0.11" in app
    for tab in ["主页面", "音色资源库", "模型配置"]:
        assert tab in app
    assert 'type="file"' in app
    assert 'accept=".txt,text/plain"' in app
    assert "上传小说" in app
    assert "确认划分章节" in app
    assert "章节列表" in app
    assert "角色列表" in app
    assert "音色选择" in app
    assert "播放音色" in app
    assert "音色描述" in app
    assert "语音具体内容" in app
    assert "当前章节" in app
    assert "确认无误" in app
    assert "语句划分" in app
    assert "utterancesByParagraph" in app
    assert "paragraph-utterances" in app
    assert "音色名称" in app
    assert "保存音色" in app
    assert "生成音色" in app
    assert "勾选删除" in app
    assert "LLM Provider" in app
    assert "TTS Provider" in app
    assert "api_key_env" in app
    assert '"api_key":' not in app
    assert "音频试听" in app
    assert 'fetch(path' in app
    assert '"/api/novels/parse"' in app
    assert "`/api/roles/${roleId}`" in app
    assert '"/api/voice-resources"' in app
    assert '"/api/voice-resources/generate"' in app
    assert '"/api/model-config"' in app
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


def test_frontend_v0_11_progress_and_large_upload_guardrails():
    """Covers v0.11 progress bars and avoiding huge full-novel textarea rendering."""
    app = read("frontend/src/App.tsx")
    styles = read("frontend/src/styles.css")

    for state_name in ["uploadProgress", "segmentationProgress", "voiceGenerationProgress"]:
      assert state_name in app

    assert "progress-bar" in app
    assert "上传小说进度" in app
    assert "语句划分进度" in app
    assert "语音生成进度" in app
    assert "MAX_NOVEL_PREVIEW_CHARS" in app
    assert "novelPreview" in app
    assert "fullNovelTextRef" in app
    assert "fullNovelTextRef.current" in app
    assert "value={novelText}" not in app
    assert "onChange={(event) => setNovelText(event.target.value)}" not in app

    assert ".progress-bar" in styles
    assert ".novel-preview" in styles


def test_v0_11_frontend_uses_unitale_style_tokens():
    """Covers v0.11 Unitale-inspired visual direction."""
    styles = read("frontend/src/styles.css")

    required_style_terms = [
        "#f1f5f9",
        "#2563eb",
        "#fef3c7",
        "#ccfbf1",
        "#f3e8ff",
        "border-radius: 8px",
        "border-radius: 12px",
        "border-bottom",
        "font-weight: 700",
    ]
    for term in required_style_terms:
        assert term in styles


def test_default_voice_samples_are_not_three_smoke_placeholder_roles():
    """Covers v0.11 removal of the old three smoke placeholder role cards."""
    app = read("frontend/src/App.tsx")
    manifest = read("assets/samples/manifest.json")

    assert "功能烟测占位，不代表最终音色质量" not in app
    assert "男声旁白" in app
    assert "年轻男" in app
    assert "御姐音" in app
    assert "narrator-male-female-smoke-test-placeholder" in manifest


def test_verification_document_records_real_environment_evidence_requirements():
    """Covers v0.11 real environment evidence requirements."""
    verification = read("docs/development/v0.11-verification.md")

    required_evidence_terms = [
        "SiliconFlow",
        "Qwen3-TTS",
        "UI 截图",
        "ffprobe",
        "真实环境",
        "mock 只能用于单元测试",
        "这个地下城长蘑菇了.txt",
        "年轻男",
        "御姐音",
        "播音腔女",
        "男声旁白",
    ]
    for term in required_evidence_terms:
        assert term in verification
