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
        "spec/v0.12-harness.md",
        "docs/development/v0.12-verification.md",
        "spec/v0.13-harness.md",
        "docs/development/v0.13-verification.md",
        "spec/v0.14-harness.md",
        "docs/development/v0.14-verification.md",
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
    assert "NovelVoice-Agent v0.14" in app
    for tab in ["主页面", "音色资源库", "模型配置"]:
        assert tab in app
    assert 'type="file"' in app
    assert 'accept=".txt,text/plain"' in app
    assert "上传小说" in app
    assert "划分章节" in app
    assert "章节列表" in app
    assert "角色列表" in app
    assert "音色选择" in app
    assert 'aria-label="播放音色"' in app
    assert "playVoicePreview" in app
    assert "新增角色" in app
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
    assert "远端模型" in app
    assert "本地模型" in app
    assert "api_key" in app
    assert "模型权重路径" in app
    for removed_field in ["LLM Provider", "TTS Provider", "api_key_env", "Timeout", "Retries", "Device Env"]:
        assert removed_field not in app
    assert "音频生成" in app
    assert "音频试听" not in app
    assert 'fetch(path' in app
    assert '"/api/novels/parse"' in app
    assert "`/api/roles/${roleId}`" in app
    assert '"/api/voice-resources"' in app
    assert '"/api/voice-resources/generate"' in app
    assert '"/api/model-config"' in app
    assert '}/speech`' in app
    assert "<audio controls" in app
    assert '"/api": "http://127.0.0.1:8000"' in vite_config
    assert '"/outputs": "http://127.0.0.1:8000"' in vite_config

    for control in ["折叠", "展开", "删除", "textarea", "select"]:
        assert control in app
    for labeled_control in ["语句文本", "选择角色", "情绪", "语言", "仅使用声纹", "语速", "音量", "其他控制文本"]:
        assert labeled_control in app
    assert "情感控制文本" not in app
    assert '<option value="voice_cloning">voice_cloning</option>' not in app

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


def test_frontend_v0_12_defers_chapter_body_and_uses_split_progress():
    """Covers v0.12 lazy chapter loading and split-chapter progress behavior."""
    app = read("frontend/src/App.tsx")
    styles = read("frontend/src/styles.css")

    assert "NovelVoice-Agent v0.14" in app
    assert "划分章节" in app
    assert "确认划分章节" not in app
    assert "chapterSplitProgress" in app
    assert "章节划分进度" in app
    assert "hasSplitChapters" in app
    assert "parseChapterIndex" in app
    assert "extractChapterBody" in app
    assert "setParagraphs([])" in app
    assert "请选择左侧章节" in app
    assert "paragraphsFromChapter(parseChapters(sampleNovel)[0])" not in app
    assert "setActiveChapterId(parsed[0]?.chapterId" not in app
    assert "setParagraphs(parsed[0] ? paragraphsFromChapter(parsed[0]) : [])" not in app

    assert "height: calc(100vh - 62px)" in styles
    assert ".sidebar" in styles and "overflow-y: auto" in styles
    assert ".main-panel" in styles and "overflow-y: auto" in styles
    assert "body {" in styles and "overflow: hidden" in styles


def test_frontend_v0_14_qwen_segmentation_and_scrollable_subpages():
    """Covers v0.14 Qwen segmentation, labeled controls, and subpage scrolling."""
    app = read("frontend/src/App.tsx")
    styles = read("frontend/src/styles.css")

    assert "NovelVoice-Agent v0.14" in app
    assert "runQwenSegmentation" in app
    assert "Qwen/Qwen3-8B" in app
    assert "已根据 Qwen/Qwen3-8B 生成可编辑语句草稿" in app
    assert "`/api/paragraphs/${paragraph.paragraphId}/segment`" in app
    assert "createLocalUtteranceDrafts" not in app
    assert "splitIntoSubSentences" not in app
    assert "paragraph not found" not in app
    assert "audioStatus: \"尚未生成\"" in app
    assert "syncCurrentChapterParagraphs" in app
    assert "`/api/chapters/${activeChapter.chapterId}/paragraphs`" in app
    assert "后端确认失败，已使用本地确认状态" not in app

    assert ".library-page," in styles
    assert ".model-page" in styles
    assert "height: calc(100vh - 62px)" in styles
    assert "overflow-y: auto" in styles


def test_frontend_v0_14_audio_module_controls_and_no_mobile_layout():
    """Covers v0.14 utterance add/delete, fold behavior, and desktop-only scope."""
    app = read("frontend/src/App.tsx")
    styles = read("frontend/src/styles.css")

    for term in [
        "addUtteranceAfter",
        "deleteUtterance",
        "添加音频生成",
        "删除音频生成",
        "EMOTION_OPTIONS",
        "<option value=\"\">空</option>",
        "取值 0.0-2.0",
        "取值 0.5-2.0",
        "压低声音、急促、带害怕情绪",
    ]:
        assert term in app

    assert "paragraph.collapsed ? null" in app
    assert "min-width: 1180px" in styles
    assert "@media (max-width" not in styles


def test_frontend_v0_14_voice_library_file_picker_generation_preview_and_model_buttons():
    """Covers v0.14 voice-library and model-configuration UI changes."""
    app = read("frontend/src/App.tsx")

    for term in [
        "voiceAudioInputRef",
        "添加参考音频文件",
        'accept="audio/*"',
        '"/api/voice-resources/reference-audio"',
        "生成音色进度",
        "generatedVoicePreview",
        "试听生成音色",
        "saveGeneratedVoiceResource",
        "saveRemoteModelConfig",
        "saveLocalModelConfig",
        "testRemoteModelLink",
        "startLocalTtsService",
        "测试链接",
        "启动服务",
        "远端模型配置保存成功",
        "本地模型配置保存成功",
        "远端模型连接成功",
        "本地 TTS 服务启动成功",
    ]:
        assert term in app


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
    """Covers v0.12 real environment evidence requirements."""
    verification = read("docs/development/v0.12-verification.md")

    required_evidence_terms = [
        "SiliconFlow",
        "Qwen3-TTS",
        "UI 截图",
        "ffprobe",
        "真实环境",
        "mock 只能用于单元测试",
        "这个地下城长蘑菇了.txt",
        "划分章节",
        "章节划分进度",
        "独立",
    ]
    for term in required_evidence_terms:
        assert term in verification
