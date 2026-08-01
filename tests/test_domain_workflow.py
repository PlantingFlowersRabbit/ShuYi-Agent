import asyncio
import base64
import json
import os
import sys
import time
import types
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.domain.audio import (
    TTSServiceError,
    TTSTextLimitError,
    VoiceJob,
    build_tts_request,
    model_control_note,
    synthesize_local_qwen3,
    synthesize_voice_design_qwen3,
    validate_wav_duration,
)
from backend.app.domain.llm import OpenAICompatibleSegmentationClient, build_segmentation_messages
from backend.app.domain.novel import ChapterWorkbench, parse_novel_text
from backend.app.domain.providers import default_provider_registry
from backend.app.domain.roles import RoleCard, RoleCollection, default_role_cards
from backend.app.domain.segmentation import validate_segmentation_result
from backend.app.domain.voices import (
    VoiceResourceCollection,
    default_voice_resources,
    generated_voice_content,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_NOVEL = ROOT / "assets/samples/novels/hongloumeng_pg24264_excerpt.txt"
REAL_SAMPLE_ROOT = Path(os.environ.get("SHUYI_REAL_SAMPLE_ROOT", ROOT / "assets/samples/real"))
REAL_NOVEL = REAL_SAMPLE_ROOT / "小说/这个地下城长蘑菇了.txt"
REAL_VOICE_ROOT = REAL_SAMPLE_ROOT / "音频"


def _test_role(
    role_id: str = "narrator",
    name: str = "旁白",
    *,
    voice_resource_id: str | None = None,
    reference_audio_path: str | None = "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
    reference_text: str | None = "测试参考文本。",
    voice_mode: str = "voice_cloning",
    design_prompt: str | None = None,
) -> RoleCard:
    return RoleCard(
        role_id=role_id,
        name=name,
        description=f"{name} 测试角色",
        voice_mode=voice_mode,
        reference_audio_path=reference_audio_path,
        reference_text=reference_text,
        design_prompt=design_prompt,
        voice_resource_id=voice_resource_id,
    )


def _post_test_role(
    client,
    *,
    role_id: str = "narrator",
    name: str = "旁白",
    reference_audio_path: str | Path | None = "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
    reference_text: str | None = "测试参考文本。",
    voice_resource_id: str | None = None,
) -> dict:
    payload = {
        "role_id": role_id,
        "name": name,
        "description": f"{name} 测试角色",
        "voice_mode": "voice_cloning",
        "reference_audio_path": str(reference_audio_path) if reference_audio_path else None,
        "reference_text": reference_text,
        "design_prompt": None,
    }
    if voice_resource_id:
        payload["voice_resource_id"] = voice_resource_id
    response = client.post("/api/v1/characters", json=payload)
    assert response.status_code == 200
    return next(role for role in response.json()["roles"] if role["role_id"] == role_id)


async def _apost_test_role(
    client,
    *,
    role_id: str = "narrator",
    name: str = "旁白",
    reference_audio_path: str | Path | None = "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
    reference_text: str | None = "测试参考文本。",
    voice_resource_id: str | None = None,
) -> dict:
    payload = {
        "role_id": role_id,
        "name": name,
        "description": f"{name} 测试角色",
        "voice_mode": "voice_cloning",
        "reference_audio_path": str(reference_audio_path) if reference_audio_path else None,
        "reference_text": reference_text,
        "design_prompt": None,
    }
    if voice_resource_id:
        payload["voice_resource_id"] = voice_resource_id
    response = await client.post("/api/v1/characters", json=payload)
    assert response.status_code == 200
    return next(role for role in response.json()["roles"] if role["role_id"] == role_id)


def test_parse_sample_novel_into_chapters_and_paragraph_workbench_gate():
    """覆盖小说解析与段落工作台人工确认门禁。"""
    chapters = parse_novel_text(SAMPLE_NOVEL.read_text(encoding="utf-8"))

    assert len(chapters) >= 1
    first = chapters[0]
    assert first.chapter_id == "chapter-0001"
    assert first.title.startswith("第一回")
    assert "甄士隱" in first.body

    workbench = ChapterWorkbench.from_chapter(first)
    assert len(workbench.visible_paragraphs) >= 3
    assert workbench.can_segment is False

    first_paragraph = workbench.visible_paragraphs[0]
    assert first_paragraph.paragraph_id == "p-0001"
    assert first_paragraph.collapsed is False

    workbench.toggle_paragraph(first_paragraph.paragraph_id)
    assert workbench.get_paragraph(first_paragraph.paragraph_id).collapsed is True

    edited_text = first_paragraph.text + "人工校正。"
    workbench.edit_paragraph(first_paragraph.paragraph_id, edited_text)
    assert workbench.get_paragraph(first_paragraph.paragraph_id).text.endswith("人工校正。")

    workbench.delete_paragraph(first_paragraph.paragraph_id)
    assert first_paragraph.paragraph_id not in [
        p.paragraph_id for p in workbench.visible_paragraphs
    ]
    assert workbench.can_segment is False

    workbench.confirm_paragraphs()
    assert workbench.can_segment is True


def test_default_roles_and_role_options_sync_to_utterance_selectors():
    """v0.4.1 默认不再预设角色，但角色选项仍随人工新增同步。"""
    roles = default_role_cards()
    assert roles == []

    collection = RoleCollection(roles)
    collection.upsert(
        {
            "role_id": "villain",
            "name": "反派",
            "description": "测试新增角色",
            "voice_mode": "voice_design",
            "reference_audio_path": None,
            "reference_text": None,
            "design_prompt": "低沉、阴冷、克制",
            "voice_resource_id": None,
        }
    )

    options = collection.utterance_role_options()
    assert {option["value"] for option in options} == {"villain"}
    assert next(option for option in options if option["value"] == "villain")["label"] == "反派"


def test_v0_11_numeric_heading_real_sample_splits_into_chapters():
    """覆盖数字标题真实样本分章。"""
    if not REAL_NOVEL.exists():
        pytest.skip(f"real sample novel not found: {REAL_NOVEL}")

    chapters = parse_novel_text(REAL_NOVEL.read_text(encoding="utf-8"))

    assert len(chapters) >= 30
    assert chapters[0].chapter_id == "chapter-0001"
    assert chapters[0].title[0].isdigit()
    assert chapters[1].title[0].isdigit()
    assert chapters[0].title != "未分章正文"
    assert chapters[0].body


def test_v0_11_voice_resources_load_real_samples_and_support_crud():
    """v0.4.1 默认音色库为空，但仍支持人工增删改查。"""
    resources = default_voice_resources(REAL_VOICE_ROOT if REAL_VOICE_ROOT.exists() else None)
    collection = VoiceResourceCollection(resources)
    assert collection.list() == []

    added = collection.upsert(
        {
            "voice_id": "voice-test",
            "name": "测试音色",
            "description": "清晰、稳定、适合角色对白",
            "reference_text": "这是一段测试语音内容。",
            "reference_audio_path": "outputs/audio/test.wav",
            "generated": False,
        }
    )
    assert added.name == "测试音色"
    assert collection.get("voice-test").description == "清晰、稳定、适合角色对白"

    updated = collection.upsert({**added.to_dict(), "description": "已修改描述"})
    assert updated.description == "已修改描述"

    collection.remove("voice-test")
    with pytest.raises(KeyError):
        collection.get("voice-test")


def test_v0_11_generated_voice_content_is_deterministic_substitute():
    """覆盖生成音色内容的确定性替身边界。"""
    content = generated_voice_content("冷静旁白", "沉稳、克制、叙事感强")

    assert "冷静旁白" in content
    assert "沉稳、克制、叙事感强" in content
    assert len(content) > 20


def test_provider_registry_preserves_openai_compatible_text_model_boundary():
    """文本模型供应商边界应兼容所有 OpenAI SDK 格式服务。"""
    registry = default_provider_registry()

    text_model = registry["openai-compatible-text"]
    assert text_model["kind"] == "chat_completions"
    assert text_model["base_url"] == ""
    assert text_model["model"] == ""
    assert text_model["api_key_env"] == "SHUYI_TEXT_MODEL_API_KEY"
    assert text_model["max_tokens"] == 1024
    assert text_model["extra_body"] == {}
    assert set(registry) == {"openai-compatible-text"}


def test_llm_segmentation_client_builds_openai_compatible_request():
    """Covers AC-LLM-01, AC-LLM-02, and provider registry API boundary."""
    provider = {
        **default_provider_registry()["openai-compatible-text"],
        "base_url": "https://models.example.test/v1",
        "model": "generic-text-model",
    }
    messages = build_segmentation_messages(
        chapter_title="第一章 初遇",
        paragraph_id="p-0001",
        paragraph_text="他说：“你好。”",
        known_roles=[{"role_id": "narrator", "name": "旁白", "description": "叙述者"}],
    )
    assert "严格 JSON" in messages[-1]["content"]
    assert "不得改写" in messages[-1]["content"]
    assert "逐字复制连续片段" in messages[-1]["content"]
    assert "单双引号都不能替换" in messages[-1]["content"]
    assert "每个 utterance 必须包含以下全部字段" in messages[-1]["content"]
    assert "voice_cloning 的 design_prompt 必须为 null" in messages[-1]["content"]
    assert "p-0001" in messages[-1]["content"]

    captured = {}

    def fake_http_post(url, headers, payload, timeout_seconds):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"paragraph_id":"p-0001","utterances":[]}',
                    }
                }
            ]
        }

    client = OpenAICompatibleSegmentationClient(
        provider=provider,
        api_key_lookup=lambda name: "test-token" if name == "SHUYI_TEXT_MODEL_API_KEY" else None,
        http_post=fake_http_post,
    )
    raw_output = client.segment(
        chapter_title="第一章 初遇",
        paragraph_id="p-0001",
        paragraph_text="他说：“你好。”",
        known_roles=[{"role_id": "narrator", "name": "旁白", "description": "叙述者"}],
    )

    assert raw_output == '{"paragraph_id":"p-0001","utterances":[]}'
    assert captured["url"] == "https://models.example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["payload"]["model"] == "generic-text-model"
    assert captured["payload"]["max_tokens"] == 1024
    assert "extra_body" not in captured["payload"]
    assert captured["payload"]["messages"] == messages


def test_v0_24_ai_segmentation_agent_reflects_once_for_text_conservation():
    """Covers v0.24 LangChain/reflection segmentation agent behavior."""
    from backend.app.domain.ai_segmentation_agent import AiSegmentationAgent

    paragraph = "“别笑了，引来魔物就麻烦了。”佩罗不耐烦地打断了笑声，“就这了，把她放下来。”"
    known_roles = [{"role_id": "narrator", "name": "旁白"}, {"role_id": "peruo", "name": "佩罗"}]
    invalid_first_pass = json.dumps(
        {
            "paragraph_id": "p-0001",
            "utterances": [
                {
                    "utterance_id": "p-0001-u-001",
                    "speaker_name": "佩罗",
                    "speaker_role_id": "peruo",
                    "voice_mode": "voice_cloning",
                    "text": "“别笑了，引来魔物就麻烦了。”",
                    "emotion": "neutral",
                    "speed": 1.0,
                    "volume": 1.0,
                    "design_prompt": None,
                    "confidence": 0.8,
                    "needs_human_review": False,
                }
            ],
        },
        ensure_ascii=False,
    )
    reflected_output = json.dumps(
        {
            "paragraph_id": "p-0001",
            "utterances": [
                {
                    "utterance_id": "p-0001-u-001",
                    "speaker_name": "佩罗",
                    "speaker_role_id": "peruo",
                    "voice_mode": "voice_cloning",
                    "text": "“别笑了，引来魔物就麻烦了。”",
                    "emotion": "neutral",
                    "speed": 1.0,
                    "volume": 1.0,
                    "design_prompt": None,
                    "confidence": 0.9,
                    "needs_human_review": False,
                },
                {
                    "utterance_id": "p-0001-u-002",
                    "speaker_name": "旁白",
                    "speaker_role_id": "narrator",
                    "voice_mode": "voice_cloning",
                    "text": "佩罗不耐烦地打断了笑声，",
                    "emotion": "neutral",
                    "speed": 1.0,
                    "volume": 1.0,
                    "design_prompt": None,
                    "confidence": 0.85,
                    "needs_human_review": False,
                },
                {
                    "utterance_id": "p-0001-u-003",
                    "speaker_name": "佩罗",
                    "speaker_role_id": "peruo",
                    "voice_mode": "voice_cloning",
                    "text": "“就这了，把她放下来。”",
                    "emotion": "neutral",
                    "speed": 1.0,
                    "volume": 1.0,
                    "design_prompt": None,
                    "confidence": 0.9,
                    "needs_human_review": False,
                },
            ],
        },
        ensure_ascii=False,
    )

    class FakeSkill:
        def __init__(self):
            self.calls: list[str] = []

        def segment(self, **kwargs):
            self.calls.append("segment")
            return invalid_first_pass

        def reflect(self, **kwargs):
            self.calls.append(f"reflect:{kwargs['validation'].error_code}")
            return reflected_output

    skill = FakeSkill()
    agent = AiSegmentationAgent(skill=skill)

    result = agent.segment(
        chapter_title="第一章",
        paragraph_id="p-0001",
        paragraph_text=paragraph,
        known_roles=known_roles,
    )

    assert result.validation.ok is True
    assert result.reflection_count == 1
    assert skill.calls == ["segment", "reflect:text_conservation_failed"]
    assert [utterance["text"] for utterance in result.validation.utterances] == [
        "“别笑了，引来魔物就麻烦了。”",
        "佩罗不耐烦地打断了笑声，",
        "“就这了，把她放下来。”",
    ]


def test_v0_14_segmentation_prompt_targets_speaker_units_not_mechanical_sentences():
    """Covers v0.14 speaker-unit segmentation requirements for OpenAI-compatible models."""
    paragraph = "“先别急着走。”林舟停在门口，“我还有一个问题。”"
    messages = build_segmentation_messages(
        chapter_title="第一章 初遇",
        paragraph_id="p-0001",
        paragraph_text=paragraph,
        known_roles=[{"role_id": "narrator", "name": "旁白"}, {"role_id": "linzhou", "name": "林舟"}],
    )
    prompt = messages[-1]["content"]

    assert "以说话人/角色为单位" in prompt
    assert "不是按句号机械拆分" in prompt
    assert "双引号" in prompt
    assert "“先别急着走。”" in prompt
    assert "林舟停在门口" in prompt
    assert "“我还有一个问题。”" in prompt
    assert "OpenAI SDK 兼容文本模型" in prompt


def test_v0_14_multi_speaker_segmentation_result_preserves_text_conservation():
    """Covers v0.14 validation for dialogue / narration / dialogue speaker units."""
    paragraph = "“别笑了，引来魔物就麻烦了。”佩罗不耐烦地打断了笑声，“就这了，把她放下来。”"
    raw = json.dumps(
        {
            "paragraph_id": "p-0001",
            "utterances": [
                {
                    "utterance_id": "p-0001-u-001",
                    "speaker_name": "佩罗",
                    "speaker_role_id": "peruo",
                    "voice_mode": "voice_cloning",
                    "text": "“别笑了，引来魔物就麻烦了。”",
                    "emotion": "",
                    "speed": 1.0,
                    "volume": 1.0,
                    "design_prompt": None,
                    "confidence": 0.88,
                    "needs_human_review": False,
                },
                {
                    "utterance_id": "p-0001-u-002",
                    "speaker_name": "旁白",
                    "speaker_role_id": "narrator",
                    "voice_mode": "voice_cloning",
                    "text": "佩罗不耐烦地打断了笑声，",
                    "emotion": "",
                    "speed": 1.0,
                    "volume": 1.0,
                    "design_prompt": None,
                    "confidence": 0.82,
                    "needs_human_review": False,
                },
                {
                    "utterance_id": "p-0001-u-003",
                    "speaker_name": "佩罗",
                    "speaker_role_id": "peruo",
                    "voice_mode": "voice_cloning",
                    "text": "“就这了，把她放下来。”",
                    "emotion": "",
                    "speed": 1.0,
                    "volume": 1.0,
                    "design_prompt": None,
                    "confidence": 0.88,
                    "needs_human_review": False,
                },
            ],
        },
        ensure_ascii=False,
    )

    result = validate_segmentation_result(
        paragraph_id="p-0001",
        paragraph_text=paragraph,
        raw_output=raw,
        known_roles=[{"role_id": "narrator", "name": "旁白"}, {"role_id": "peruo", "name": "佩罗"}],
    )

    assert result.ok is True
    assert [item["text"] for item in result.utterances] == [
        "“别笑了，引来魔物就麻烦了。”",
        "佩罗不耐烦地打断了笑声，",
        "“就这了，把她放下来。”",
    ]


def test_segmentation_schema_text_conservation_and_unknown_role_review():
    """Covers AC-FLOW-07 and AC-LLM-02 through AC-LLM-07."""
    paragraph = "他说：“你好。”"
    known_roles = [{"role_id": "narrator", "name": "旁白"}]
    raw = json.dumps(
        {
            "paragraph_id": "p-0001",
            "utterances": [
                {
                    "utterance_id": "p-0001-u-001",
                    "speaker_name": "未知角色",
                    "speaker_role_id": "stranger",
                    "voice_mode": "voice_design",
                    "text": "他说：“你好。”",
                    "emotion": "neutral",
                    "speed": 1.0,
                    "volume": 1.0,
                    "design_prompt": "清亮自然说话",
                    "confidence": 0.42,
                    "needs_human_review": False,
                }
            ],
        },
        ensure_ascii=False,
    )

    result = validate_segmentation_result(
        paragraph_id="p-0001",
        paragraph_text=paragraph,
        raw_output=raw,
        known_roles=known_roles,
    )

    assert result.ok is True
    utterance = result.utterances[0]
    assert utterance["speaker_role_id"] is None
    assert utterance["needs_human_review"] is True
    assert utterance["text"] == paragraph

    utterance["text"] = "他说你好。"
    broken_raw = json.dumps(
        {"paragraph_id": "p-0001", "utterances": [utterance]}, ensure_ascii=False
    )
    broken = validate_segmentation_result(
        paragraph_id="p-0001",
        paragraph_text=paragraph,
        raw_output=broken_raw,
        known_roles=known_roles,
    )
    assert broken.ok is False
    assert broken.error_code == "text_conservation_failed"
    assert broken.raw_output == broken_raw


def test_segmentation_allows_one_json_repair_attempt_only():
    """Covers AC-LLM-02 and AC-LLM-05."""
    paragraph = "旁白文本"
    repaired_payload = {
        "paragraph_id": "p-0002",
        "utterances": [
            {
                "utterance_id": "p-0002-u-001",
                "speaker_name": "旁白",
                "speaker_role_id": "narrator",
                "voice_mode": "voice_cloning",
                "text": paragraph,
                "emotion": "neutral",
                "speed": 1.0,
                "volume": 1.0,
                "design_prompt": None,
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ],
    }

    calls = []

    def repair_once(raw_output):
        calls.append(raw_output)
        return json.dumps(repaired_payload, ensure_ascii=False)

    result = validate_segmentation_result(
        paragraph_id="p-0002",
        paragraph_text=paragraph,
        raw_output="```json\nnot-json\n```",
        known_roles=[{"role_id": "narrator", "name": "旁白"}],
        repair_json=repair_once,
    )

    assert result.ok is True
    assert len(calls) == 1

    failed = validate_segmentation_result(
        paragraph_id="p-0002",
        paragraph_text=paragraph,
        raw_output="not-json",
        known_roles=[{"role_id": "narrator", "name": "旁白"}],
        repair_json=lambda raw: "still not json",
    )
    assert failed.ok is False
    assert failed.error_code == "invalid_json"


def test_v0_25_whole_paragraph_drafts_are_backend_reusable():
    """v0.25 requires confirm flow and LangGraph workflow to share backend draft creation."""
    from backend.app.domain.dubbing_workflow import create_whole_paragraph_utterance_drafts
    from backend.app.domain.novel import ParagraphModule

    paragraphs = [
        ParagraphModule(paragraph_id="p-0001", text="旁白第一段。", confirmed=True),
        ParagraphModule(paragraph_id="p-0002", text="“你好。”", confirmed=True),
    ]

    drafts = create_whole_paragraph_utterance_drafts(paragraphs)

    assert [draft["utterance_id"] for draft in drafts] == ["p-0001-u-001", "p-0002-u-001"]
    assert [draft["paragraph_id"] for draft in drafts] == ["p-0001", "p-0002"]
    assert [draft["text"] for draft in drafts] == ["旁白第一段。", "“你好。”"]
    assert all(draft["speaker_role_id"] is None for draft in drafts)
    assert all(draft["needs_human_review"] is True for draft in drafts)


def test_v0_25_role_analysis_workflow_pauses_with_human_editable_candidates():
    """The LangGraph workflow first returns role suggestions and waits for role-list edits."""
    from backend.app.domain.dubbing_workflow import DubbingWorkflow, RoleAnalysisCandidate

    class FakeSkill:
        def analyze_roles(self, **kwargs):
            assert "测试角色甲" in kwargs["chapter_text"]
            return [
                RoleAnalysisCandidate(
                    name="测试角色甲",
                    aliases=["角色甲"],
                    gender="女",
                    profile="测试章节中的主角，紧张但倔强",
                    voice_direction="年轻女性，惊慌但清晰",
                    evidence=["测试角色甲正在挣脱绳索"],
                    confidence=0.84,
                    needs_human_review=True,
                )
            ]

    workflow = DubbingWorkflow(role_skill=FakeSkill(), segmentation_service=None)
    result = workflow.start_role_analysis(
        chapter_id="chapter-0001",
        chapter_title="第一章 测试章节",
        paragraphs=[{"paragraph_id": "p-0001", "text": "测试角色甲正在挣脱绳索。"}],
        existing_roles=[{"role_id": "narrator", "name": "旁白"}],
    )

    assert result.status == "waiting_for_roles"
    assert result.thread_id
    assert result.message == "请先把所需角色添加到角色列表中，或绑定到已有角色。"
    assert result.role_candidates[0].name == "测试角色甲"
    assert result.role_candidates[0].needs_human_review is True


def test_v0_25_workflow_resume_preserves_existing_roles_segments_ambiguous_paragraphs_and_streams_updates():
    """Resume creates drafts and lets 配音编排 Agent split/select in one Agent response."""
    from backend.app.domain.dubbing_workflow import DubbingWorkflow

    class FakeRoleSkill:
        def __init__(self):
            self.calls = []

        def analyze_roles(self, **kwargs):
            return []

        def choose_roles_batch(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "items": [
                    {
                        "statement_id": "p-0002-u-001",
                        "action": "split_and_select",
                        "reason": "dialogue plus narration",
                        "utterances": [
                            {
                                "text": "“你好。”",
                                "role_id": "hero",
                                "confidence": 0.76,
                                "reason": "dialogue cue",
                            },
                            {
                                "text": "她挥手。",
                                "role_id": "narrator",
                                "confidence": 0.91,
                                "reason": "narration",
                            },
                        ],
                    }
                ]
            }

    class ForbiddenSegmentationService:
        def segment_paragraph(self, **kwargs):
            raise AssertionError("配音编排 Agent must not call the standalone AI语句划分 service")

    events = []
    role_skill = FakeRoleSkill()
    workflow = DubbingWorkflow(
        role_skill=role_skill, segmentation_service=ForbiddenSegmentationService()
    )
    start = workflow.start_role_analysis(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        paragraphs=[
            {"paragraph_id": "p-0001", "text": "旁白第一段。"},
            {"paragraph_id": "p-0002", "text": "“你好。”她挥手。"},
        ],
        existing_roles=[
            {"role_id": "narrator", "name": "旁白"},
            {"role_id": "hero", "name": "测试角色甲"},
        ],
    )

    result = workflow.resume_after_roles(
        thread_id=start.thread_id,
        roles=[{"role_id": "narrator", "name": "旁白"}, {"role_id": "hero", "name": "测试角色甲"}],
        existing_utterances_by_paragraph={
            "p-0001": [
                {
                    "utterance_id": "p-0001-u-001",
                    "paragraph_id": "p-0001",
                    "text": "旁白第一段。",
                    "speaker_role_id": "narrator",
                    "speaker_name": "旁白",
                }
            ]
        },
        on_role_selected=events.append,
    )

    assert result.status == "completed"
    assert [[item["text"] for item in call["statements"]] for call in role_skill.calls] == [
        ["“你好。”她挥手。"]
    ]
    assert result.utterances_by_paragraph["p-0001"][0]["speaker_role_id"] == "narrator"
    assert result.utterances_by_paragraph["p-0002"][0]["speaker_role_id"] == "hero"
    assert result.utterances_by_paragraph["p-0002"][1]["speaker_role_id"] == "narrator"
    assert [event["utterance_id"] for event in events] == ["p-0002-u-001", "p-0002-u-002"]
    assert [event["speaker_role_id"] for event in events] == ["hero", "narrator"]


def test_v0_25_workflow_returns_readable_failure_when_split_and_select_text_conservation_fails():
    """Invalid model output must not be silently rewritten or accepted."""
    from backend.app.domain.dubbing_workflow import DubbingWorkflow

    class FakeRoleSkill:
        def analyze_roles(self, **kwargs):
            return []

        def choose_roles_batch(self, **kwargs):
            return {
                "items": [
                    {
                        "statement_id": "p-0001-u-001",
                        "action": "split_and_select",
                        "reason": "bad split",
                        "utterances": [
                            {
                                "text": "“你好。”",
                                "role_id": "hero",
                                "confidence": 0.8,
                                "reason": "dropped narration",
                            }
                        ],
                    }
                ]
            }

    class ForbiddenSegmentationService:
        def segment_paragraph(self, **kwargs):
            raise AssertionError("配音编排 Agent must not call the standalone AI语句划分 service")

    workflow = DubbingWorkflow(
        role_skill=FakeRoleSkill(), segmentation_service=ForbiddenSegmentationService()
    )
    start = workflow.start_role_analysis(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        paragraphs=[{"paragraph_id": "p-0001", "text": "“你好。”她挥手。"}],
        existing_roles=[],
    )

    result = workflow.resume_after_roles(
        thread_id=start.thread_id,
        roles=[{"role_id": "narrator", "name": "旁白"}, {"role_id": "hero", "name": "测试角色甲"}],
        existing_utterances_by_paragraph={},
    )

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure["paragraph_id"] == "p-0001"
    assert result.failure["error_code"] == "invalid_split_and_select"
    assert "完整保留原台词文本" in result.failure["message"]
    assert result.utterances_by_paragraph == {}


def test_tts_request_validation_and_voice_job_traceability():
    """Covers AC-ROLE-03, AC-ROLE-04, and AC-AUDIO-07."""
    narrator = _test_role()
    utterance = {
        "utterance_id": "p-0001-u-001",
        "text": "待合成文本",
        "voice_mode": "voice_cloning",
        "emotion": "紧张",
        "other_control_text": "压低声音，像在躲避追兵。",
        "language": "Auto",
        "x_vector_only": True,
        "speed": 1.2,
        "volume": 0.8,
    }

    request = build_tts_request(utterance, narrator)
    assert request["input"] == "待合成文本"
    assert request["audio_sample_path"].endswith(".wav")
    assert request["ref_text"]
    assert request["response_format"] == "wav"
    assert request["language"] == "Auto"
    assert request["reusable_prompt"] == request["ref_text"]
    assert request["x_vector_only"] is True
    assert request["emotion"] == "紧张"
    assert request["other_control_text"] == "压低声音，像在躲避追兵。"
    assert request["speed"] == 1.2
    assert request["volume"] == 0.8
    assert "紧张" in request["control_instruct"]
    assert "压低声音" in request["control_instruct"]
    assert "Qwen3-TTS-12Hz-1.7B-Base" in model_control_note("voice_cloning")
    assert "中文自然语言" in model_control_note("voice_design")

    missing_reference = narrator.with_updates(reference_audio_path=None)
    with pytest.raises(ValueError, match="声音克隆需要参考音频"):
        build_tts_request(utterance, missing_reference)

    design_role = _test_role(
        role_id="design_role",
        name="设计音色角色",
        voice_mode="voice_design",
        reference_audio_path=None,
        reference_text=None,
    ).with_updates(
        voice_mode="voice_design",
        design_prompt=None,
        reference_audio_path=None,
        reference_text=None,
    )
    with pytest.raises(ValueError, match="声音设计需要音色描述"):
        build_tts_request(
            {
                "utterance_id": "p-0001-u-001",
                "text": "待合成文本",
                "voice_mode": "voice_design",
                "other_control_text": "",
            },
            design_role,
        )

    job = VoiceJob(
        voice_job_id="vj-0001",
        utterance_id="p-0001-u-001",
        role_id="narrator",
        voice_mode="voice_cloning",
        provider="local-qwen3-tts",
        request_text="待合成文本",
        reference_audio_path="assets/samples/voices/cmn_qixinxieli_canonni_cc0_loop20s.wav",
        reference_text="齐心协力。",
        response_format="wav",
        output_path="outputs/audio/vj-0001.wav",
        status="succeeded",
        error=None,
    )
    trace = job.to_dict()
    assert trace["utterance_id"] == "p-0001-u-001"
    assert trace["role_id"] == "narrator"
    assert trace["provider"] == "local-qwen3-tts"
    assert trace["reference_audio_path"].endswith(".wav")
    assert trace["reference_text"]
    assert trace["output_path"].endswith(".wav")


def test_v0_12_voice_clone_request_keeps_controls_out_of_qwen_payload(tmp_path):
    """Covers v0.12 Base model voice clone request shape and deferred controls."""
    reference_audio = tmp_path / "reference.wav"
    service_audio = tmp_path / "service.wav"
    write_valid_wav(reference_audio)
    write_valid_wav(service_audio)

    role = _test_role(
        reference_audio_path=str(reference_audio),
        reference_text="这是一段短参考音频。",
    )
    request = build_tts_request(
        {
            "utterance_id": "p-0001-u-001",
            "text": "目标生成台词",
            "voice_mode": "voice_cloning",
            "emotion": "开心",
            "other_control_text": "带一点笑意",
            "speed": 0.5,
            "volume": 1.5,
        },
        role,
    )

    assert request["language"] == "Auto"
    assert request["audio_sample_path"] == str(reference_audio)
    assert request["reusable_prompt"] == "这是一段短参考音频。"
    assert request["control_instruct"] == "开心地说；较慢地说；大声地说；带一点笑意"

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return service_audio.read_bytes()

    def fake_urlopen(http_request, timeout=120):
        captured["payload"] = json.loads(http_request.data.decode("utf-8"))
        return FakeResponse()

    with patch("backend.app.domain.audio.urllib.request.urlopen", fake_urlopen):
        duration = synthesize_local_qwen3(
            request,
            output_path=tmp_path / "out.wav",
            service_base_url="http://127.0.0.1:7811",
        )

    assert duration == 0.75
    assert captured["payload"]["input"] == "目标生成台词"
    assert captured["payload"]["ref_text"] == "这是一段短参考音频。"
    assert captured["payload"]["language"] == "Auto"
    assert "emotion_control_text" not in captured["payload"]
    assert "control_instruct" not in captured["payload"]
    assert "speed" not in captured["payload"]
    assert "volume" not in captured["payload"]


def test_synthesize_local_qwen3_preserves_reference_audio_suffix_for_json_clone(tmp_path):
    """Covers v0.23 MP3 reference audio going through the JSON voice-clone path."""
    reference_audio = tmp_path / "reference.mp3"
    reference_audio.write_bytes(b"ID3 fake mp3 bytes")
    service_audio = tmp_path / "service.wav"
    write_valid_wav(service_audio)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return service_audio.read_bytes()

    def fake_urlopen(http_request, timeout=120):
        captured["payload"] = json.loads(http_request.data.decode("utf-8"))
        return FakeResponse()

    with patch("backend.app.domain.audio.urllib.request.urlopen", fake_urlopen):
        synthesize_local_qwen3(
            {
                "input": "目标生成台词",
                "audio_sample_path": str(reference_audio),
                "ref_text": "参考文本",
                "language": "Auto",
                "response_format": "wav",
            },
            output_path=tmp_path / "out.wav",
            service_base_url="http://127.0.0.1:7811",
        )

    assert captured["payload"]["audio_sample_suffix"] == ".mp3"


def test_fastapi_app_exposes_v0_4_resource_boundaries():
    """验证 v0.4 多人有声书工作台的资源边界。"""
    pytest.importorskip("fastapi")
    from backend.app.api.app import create_app

    app = create_app()
    routes = {}
    for route in app.routes:
        if hasattr(route, "methods"):
            routes.setdefault(route.path, set()).update(route.methods)

    expected = [
        ("/api/v1/books/parse", "POST"),
        ("/api/v1/books/agent-chapter-split", "POST"),
        ("/api/v1/chapters", "GET"),
        ("/api/v1/chapters/{chapter_id}", "GET"),
        ("/api/v1/chapters/{chapter_id}/paragraphs", "PUT"),
        ("/api/v1/chapters/{chapter_id}/agent-runs", "POST"),
        ("/api/v1/paragraphs/{paragraph_id}", "PATCH"),
        ("/api/v1/paragraphs/{paragraph_id}/segment", "POST"),
        ("/api/v1/agent-runs/{thread_id}/dubbing-arrangement", "POST"),
        ("/api/v1/agent-runs/{thread_id}/events", "POST"),
        ("/api/v1/characters", "GET"),
        ("/api/v1/characters", "POST"),
        ("/api/v1/characters/{role_id}", "PATCH"),
        ("/api/v1/voice-profiles", "GET"),
        ("/api/v1/voice-profiles", "POST"),
        ("/api/v1/voice-profiles/generate", "POST"),
        ("/api/v1/voice-profiles/reference-audio", "POST"),
        ("/api/v1/voice-profiles/{voice_id}", "PATCH"),
        ("/api/v1/voice-profiles/{voice_id}", "DELETE"),
        ("/api/v1/voice-profiles/{voice_id}/audio", "GET"),
        ("/api/v1/model-config", "GET"),
        ("/api/v1/model-config", "PATCH"),
        ("/api/v1/model-config/secret-exchange", "POST"),
        ("/api/v1/model-config/text-model/test", "POST"),
        ("/api/v1/model-config/tts/test", "POST"),
        ("/api/v1/model-config/tts/start", "POST"),
        ("/api/v1/dubbing-segments/{utterance_id}/dubbing-jobs", "POST"),
        ("/api/v1/dubbing-jobs/{chapter_id}", "POST"),
        ("/api/v1/exports/{chapter_id}", "POST"),
    ]
    for path, method in expected:
        assert method in routes[path]


def test_fastapi_v0_11_voice_resource_crud_and_role_voice_sync(tmp_path):
    """Covers v0.11 voice resource API and role selection synchronization."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    source_audio = tmp_path / "api-test.wav"
    write_valid_wav(source_audio)
    voice_store = tmp_path / "voice-store"

    with patch.object(app_module, "OUTPUT_VOICE_RESOURCE_DIR", voice_store):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        list_response = client.get("/api/v1/voice-profiles")
        assert list_response.status_code == 200
        assert list_response.json()["voices"] == []

        create_response = client.post(
            "/api/v1/voice-profiles",
            json={
                "name": "接口测试音色",
                "description": "明亮、自然、适合少年角色",
                "reference_text": "接口测试语音内容。",
                "reference_audio_path": str(source_audio),
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()["voice"]
        assert created["voice_id"].startswith("voice-")
        assert created["name"] == "接口测试音色"
        assert created["reference_audio_path"] == (
            f"/api/v1/voice-profiles/{created['voice_id']}/audio"
        )
        created_audio_path = next(voice_store.glob(f"{created['voice_id']}.*"))
        assert created_audio_path.exists()

        role = _post_test_role(
            client,
            role_id="narrator",
            name="旁白",
            voice_resource_id=created["voice_id"],
        )
        assert role["voice_resource_id"] == created["voice_id"]
        assert role["reference_audio_path"] == created["reference_audio_path"]
        assert role["reference_text"] == "接口测试语音内容。"

        update_response = client.patch(
            f"/api/v1/voice-profiles/{created['voice_id']}",
            json={"description": "已通过接口修改"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["voice"]["description"] == "已通过接口修改"

        delete_response = client.delete(f"/api/v1/voice-profiles/{created['voice_id']}")
    assert delete_response.status_code == 200
    remaining_ids = {voice["voice_id"] for voice in delete_response.json()["voices"]}
    assert created["voice_id"] not in remaining_ids


def test_fastapi_v0_141_generated_voice_attempts_voicedesign_model_before_substitute(tmp_path):
    """Covers v0.141 generated voice preview using VoiceDesign when the service supports it."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    calls = []

    def fake_voice_design(request, *, output_path, service_base_url=None):
        calls.append(
            {"request": request, "output_path": output_path, "service_base_url": service_base_url}
        )
        write_valid_wav(output_path)
        return 0.75

    with (
        patch.object(app_module, "OUTPUT_VOICE_RESOURCE_DIR", tmp_path),
        patch.object(app_module, "synthesize_voice_design_qwen3", fake_voice_design),
    ):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        before_count = len(client.get("/api/v1/voice-profiles").json()["voices"])
        generated = client.post(
            "/api/v1/voice-profiles/generate",
            json={
                "name": "生成旁白",
                "description": "沉稳、叙事、颗粒感轻",
                "reference_text": "这是一段用于试听新音色的语音。",
            },
        )
        after_generate_count = len(client.get("/api/v1/voice-profiles").json()["voices"])

        assert generated.status_code == 200
        data = generated.json()
        voice = data["voice"]
        assert voice["generated"] is True
        assert voice["voice_id"].startswith("preview-")
        assert voice["reference_text"] == "这是一段用于试听新音色的语音。"
        assert voice["reference_audio_path"] == f"/api/v1/voice-profiles/{voice['voice_id']}/audio"
        assert data["audio_url"].startswith("/api/v1/downloads/voice-profiles/")
        assert data["generation_status"] == "succeeded"
        assert data["generation_note"] == "已生成试听音色。"
        assert calls[0]["request"]["input"] == "这是一段用于试听新音色的语音。"
        assert calls[0]["request"]["instruct"] == "沉稳、叙事、颗粒感轻"
        assert calls[0]["request"]["language"] == "Auto"
        assert before_count == after_generate_count

        saved = client.post(
            "/api/v1/voice-profiles",
            json={
                "name": voice["name"],
                "description": voice["description"],
                "reference_text": voice["reference_text"],
                "reference_audio_path": voice["reference_audio_path"],
                "generated": True,
            },
        )
        assert saved.status_code == 200
        assert len(saved.json()["voices"]) == before_count + 1


def test_fastapi_v0_141_generated_voice_substitute_returns_neutral_preview_note(tmp_path):
    """Covers v0.141 fallback preview when generated voice synthesis is unavailable."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    def unavailable_voice_design(request, *, output_path, service_base_url=None):
        raise TTSServiceError("voice design endpoint unavailable")

    with (
        patch.object(app_module, "OUTPUT_VOICE_RESOURCE_DIR", tmp_path),
        patch.object(app_module, "synthesize_voice_design_qwen3", unavailable_voice_design),
    ):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        generated = client.post(
            "/api/v1/voice-profiles/generate",
            json={
                "name": "生成旁白",
                "description": "沉稳、叙事、颗粒感轻",
                "reference_text": "这是一段用于试听新音色的语音。",
            },
        )

    assert generated.status_code == 200
    data = generated.json()
    assert data["generation_status"] == "substitute"
    assert data["generation_note"] == "已生成本地预览音频。"
    assert data["model_requirement"] is None
    assert validate_wav_duration(tmp_path / "preview-0001.wav") == 0.75


def test_fastapi_v0_24_speech_uses_selected_voice_resource_override(tmp_path):
    """Covers v0.24 role-to-voice sync when a newly selected voice is used for speech."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    reference_audio = tmp_path / "preview-0002.wav"
    write_valid_wav(reference_audio)
    captured = {}

    def fake_synthesize(request, *, output_path, service_base_url=None):
        captured["request"] = request
        captured["service_base_url"] = service_base_url
        write_valid_wav(output_path)
        return 0.75

    voice_store = tmp_path / "voice-store"
    with (
        patch.object(app_module, "OUTPUT_AUDIO_DIR", tmp_path),
        patch.object(app_module, "OUTPUT_VOICE_RESOURCE_DIR", voice_store),
        patch.object(app_module, "synthesize_local_qwen3", fake_synthesize),
    ):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        voice_response = client.post(
            "/api/v1/voice-profiles",
            json={
                "voice_id": "voice-male-2",
                "name": "男2",
                "description": "雄壮苍老的声音",
                "reference_text": "这是一段用于试听新音色的语音。",
                "reference_audio_path": str(reference_audio),
                "generated": True,
            },
        )
        assert voice_response.status_code == 200
        copied_audio_path = voice_store / "voice-male-2.wav"
        assert copied_audio_path.exists()

        stale_role = _post_test_role(
            client,
            role_id="narrator_2",
            name="旁白2",
            reference_audio_path=reference_audio,
            reference_text="齐心协力",
        )
        assert stale_role["reference_text"] == "齐心协力"

        speech = client.post(
            "/api/v1/dubbing-segments/p-0001-u-001/dubbing-jobs",
            json={
                "role_id": "narrator_2",
                "voice_resource_id": "voice-male-2",
                "text": "待合成文本",
                "voice_mode": "voice_cloning",
                "language": "Auto",
            },
        )

    assert speech.status_code == 200
    data = speech.json()
    assert captured["request"]["audio_sample_path"] == str(copied_audio_path)
    assert captured["request"]["ref_text"] == "这是一段用于试听新音色的语音。"
    assert data["voice_job"]["reference_audio_path"] == str(copied_audio_path)
    assert data["voice_job"]["reference_text"] == "这是一段用于试听新音色的语音。"


def test_voice_design_request_uses_qwen_endpoint_when_available(tmp_path):
    """Covers v0.141 VoiceDesign model request shape."""
    audio_bytes = tmp_path / "design.wav"
    write_valid_wav(audio_bytes)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return audio_bytes.read_bytes()

    def fake_urlopen(request, timeout=120):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    with patch("backend.app.domain.audio.urllib.request.urlopen", fake_urlopen):
        output = tmp_path / "preview.wav"
        duration = synthesize_voice_design_qwen3(
            {
                "input": "这是一段用于试听新音色的语音。",
                "instruct": "沉稳、叙事、颗粒感轻",
                "language": "Auto",
                "response_format": "wav",
            },
            output_path=output,
            service_base_url="http://127.0.0.1:7811",
        )

    assert duration == 0.75
    assert captured["url"] == "http://127.0.0.1:7811/v1/audio/voice-design"
    assert captured["payload"]["input"] == "这是一段用于试听新音色的语音。"
    assert captured["payload"]["instruct"] == "沉稳、叙事、颗粒感轻"
    assert captured["payload"]["language"] == "Auto"


def test_fastapi_v0_14_reference_audio_upload_saves_local_file(tmp_path):
    """Covers v0.14 file-picker style reference audio ingestion without typing a path."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    with patch.object(app_module, "OUTPUT_VOICE_RESOURCE_DIR", tmp_path):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        response = client.post(
            "/api/v1/voice-profiles/reference-audio",
            files={"file": ("角色 试听.wav", b"RIFF$\x00\x00\x00WAVE", "audio/wav")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["reference_audio_path"].startswith("/api/v1/downloads/voice-profiles/")
    assert data["filename"].endswith(".wav")
    assert (tmp_path / data["filename"]).exists()


def test_fastapi_v0_21_voice_resources_are_materialized_into_one_directory(tmp_path):
    """Covers v0.21 unified storage while v0.4.1 avoids auto-loading bundled voices."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    sample_root = tmp_path / "real-samples"
    sample_voice_dir = sample_root / "voice-a"
    sample_voice_dir.mkdir(parents=True)
    external_audio = sample_voice_dir / "voice-a.mp3"
    external_audio.write_bytes(b"ID3 fake mp3 bytes")
    (sample_voice_dir / "语音内容.txt").write_text("光柱最终落在那株神木幼苗上。", encoding="utf-8")
    voice_store = tmp_path / "voice-store"

    with (
        patch.object(app_module, "REAL_VOICE_ROOT", sample_root),
        patch.object(app_module, "OUTPUT_VOICE_RESOURCE_DIR", voice_store),
    ):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        listed = client.get("/api/v1/voice-profiles")

        new_source = tmp_path / "external-new.wav"
        write_valid_wav(new_source)
        created = client.post(
            "/api/v1/voice-profiles",
            json={
                "voice_id": "voice-external",
                "name": "外部音色",
                "description": "外部路径导入",
                "reference_text": "外部音色参考文本。",
                "reference_audio_path": str(new_source),
            },
        )

    assert listed.status_code == 200
    assert listed.json()["voices"] == []

    assert created.status_code == 200
    created_path = next(voice_store.glob("voice-external.*"))
    assert created_path.exists()
    assert created_path != new_source


def test_fastapi_v0_14_model_config_boundaries_and_feedback_endpoints(monkeypatch):
    """Covers v0.14 split model-config save/test/start API behavior."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})

    config_response = client.get("/api/v1/model-config")
    assert config_response.status_code == 200
    config = config_response.json()["config"]
    assert config["text_model"]["base_url"] == ""
    assert config["text_model"]["model"] == ""
    assert config["text_model"]["has_api_key"] is False
    assert "llm" not in config
    assert "chapter_agent" not in config
    assert config["tts"]["base_url"] == "http://127.0.0.1:7811"
    assert config["tts"]["model_path"] == app_module.DEFAULT_BASE_MODEL_PATH
    assert config["tts"]["voice_design_model_path"] == app_module.DEFAULT_VOICE_DESIGN_MODEL_PATH

    text_model_save = client.patch(
        "/api/v1/model-config",
        json={
            "text_model": {
                "base_url": "https://api.example.test/v1",
                "model": "remote-test-model",
            },
        },
    )
    assert text_model_save.status_code == 200
    updated = text_model_save.json()["config"]
    assert updated["text_model"]["base_url"] == "https://api.example.test/v1"
    assert updated["text_model"]["model"] == "remote-test-model"
    assert updated["text_model"]["has_api_key"] is False

    local_save = client.patch(
        "/api/v1/model-config",
        json={
            "tts": {
                "base_url": "http://127.0.0.1:7811",
                "model_path": "/models/qwen3-tts",
                "voice_design_model_path": "/models/qwen3-tts-voice-design",
            },
        },
    )
    assert local_save.status_code == 200
    updated = local_save.json()["config"]
    assert updated["tts"]["model_path"] == "/models/qwen3-tts"
    assert updated["tts"]["voice_design_model_path"] == "/models/qwen3-tts-voice-design"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"data":[]}'

    captured_model_urls = []

    def capture_model_urlopen(request, timeout=10):
        captured_model_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setenv("SHUYI_TEXT_MODEL_API_KEY", "text-model-test-key")
    monkeypatch.setattr(app_module.urllib.request, "urlopen", capture_model_urlopen)
    test_link = client.post(
        "/api/v1/model-config/text-model/test",
        json={"text_model": {"base_url": "https://api.example.test/v1", "model": "remote-test-model"}},
    )
    assert test_link.status_code == 200
    assert test_link.json()["ok"] is True
    assert "文本模型连接成功" in test_link.json()["message"]
    assert captured_model_urls[-1] == "https://api.example.test/v1/models"

    calls = []

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    class FakeHealthResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok":true,"voice_clone":true,"voice_design":true,"voice_design_capable":true}'

    health_attempts = {"count": 0}

    def fake_health_urlopen(request, timeout=10):
        health_attempts["count"] += 1
        if health_attempts["count"] == 1:
            raise OSError("connection refused")
        return FakeHealthResponse()

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_health_urlopen)
    monkeypatch.setattr(
        app_module.subprocess, "Popen", lambda *args, **kwargs: calls.append(args) or FakeProcess()
    )
    start = client.post("/api/v1/model-config/tts/start", json={})
    assert start.status_code == 200
    assert start.json()["ok"] is True
    assert "模型加载完成" in start.json()["message"]
    assert calls
    command = calls[0][0]
    assert "--model-path" in command
    assert "--voice-design-model-path" in command
    assert "/models/qwen3-tts" in command
    assert "/models/qwen3-tts-voice-design" in command


def test_fastapi_v0_23_tts_start_waits_for_health_before_reporting_success(monkeypatch):
    """Covers v0.23 startup feedback: Popen alone is not a successful local TTS start."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    class FakeProcess:
        pid = 5252

        def poll(self):
            return None

    monkeypatch.setenv("SHUYI_TTS_STARTUP_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        app_module.urllib.request,
        "urlopen",
        lambda request, timeout=10: (_ for _ in ()).throw(OSError("connection refused")),
    )

    client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
    response = client.post(
        "/api/v1/model-config/tts/start",
        json={
            "tts": {
                "base_url": "http://127.0.0.1:7811",
                "model_path": "/models/qwen3-tts",
                "voice_design_model_path": "/models/qwen3-tts-voice-design",
            },
        },
    )

    assert response.status_code == 503
    assert "尚未完成启动" in response.text
    assert "模型加载" in response.text


def test_fastapi_v0_21_long_tts_text_returns_user_actionable_error(tmp_path):
    """Covers v0.21 clear feedback when one utterance exceeds the local TTS boundary."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    long_text = (
        "【技能：骑术LV4、元素亲和（水、光）LV4、魔力储存LV3、魔力操控LV4、光系魔法LV4、"
        "水系魔法LV3、布甲精通LV2、匕首精通LV2、魔法抗性LV6、物理抗性LV6、精神抗性LV6、"
        "腐蚀抗性LV6、麻痹抗性LV6、高温抗性LV6、寒冷抗性LV6、眩晕抗性LV6、水下适应LV6、"
        "星象占卜LV1、古精灵语LV2、生命回复LV4】"
    )

    def text_limit(request, *, output_path, service_base_url=None):
        raise TTSTextLimitError(
            "当前语句文本长度 167 字，超过本地 TTS 单条建议上限 120 字；"
            "已使用最大 max_new_tokens=8192，仍不适合继续等待。请手动缩短文本或拆成多条音频生成。"
        )

    with (
        patch.object(app_module, "OUTPUT_AUDIO_DIR", tmp_path),
        patch.object(app_module, "synthesize_local_qwen3", text_limit),
    ):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        reference_audio = tmp_path / "narrator-reference.wav"
        write_valid_wav(reference_audio)
        _post_test_role(client, reference_audio_path=reference_audio)
        response = client.post(
            "/api/v1/dubbing-segments/p-0001-u-001/dubbing-jobs",
            json={
                "role_id": "narrator",
                "text": long_text,
                "voice_mode": "voice_cloning",
            },
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "当前语句文本长度" in detail
    assert "max_new_tokens=8192" in detail
    assert "请手动缩短文本或拆成多条音频生成" in detail


def test_synthesize_local_qwen3_preflights_configurable_text_limit(tmp_path, monkeypatch):
    """Covers v0.21 local request guard before long text reaches the model server."""
    reference_audio = tmp_path / "reference.wav"
    write_valid_wav(reference_audio)
    monkeypatch.setenv("SHUYI_TTS_MAX_INPUT_CHARS", "12")

    with pytest.raises(TTSTextLimitError) as exc_info:
        synthesize_local_qwen3(
            {
                "input": "这是一段明显过长的待合成文本",
                "audio_sample_path": str(reference_audio),
                "ref_text": "参考文本",
                "language": "Chinese",
                "response_format": "wav",
            },
            output_path=tmp_path / "out.wav",
            service_base_url="http://127.0.0.1:7811",
        )

    message = str(exc_info.value)
    assert "当前语句文本长度" in message
    assert "单条上限 12 字" in message
    assert "请手动缩短文本或拆成多条音频生成" in message


def test_fastapi_v0_14_syncs_current_local_paragraphs_before_confirmation():
    """Covers v0.14 fix for stale backend paragraph state after local edits/deletes."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app

    client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
    response = client.put(
        "/api/v1/chapters/chapter-0001/paragraphs",
        json={
            "title": "第一章 测试章节",
            "paragraphs": [
                {
                    "paragraph_id": "p-0002",
                    "text": "测试角色甲正在挣脱绳索。",
                    "collapsed": False,
                    "deleted": False,
                }
            ],
            "confirm": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["can_segment"] is True
    assert [paragraph["paragraph_id"] for paragraph in data["paragraphs"]] == ["p-0002"]
    assert data["utterance_drafts"][0]["utterance_id"] == "p-0002-u-001"
    assert data["utterance_drafts"][0]["text"] == "测试角色甲正在挣脱绳索。"
    assert data["utterance_drafts"][0]["speaker_role_id"] is None
    missing_key = client.post("/api/v1/paragraphs/p-0002/segment", json={})
    assert missing_key.status_code == 503
    assert "段落不存在" not in missing_key.text


def test_fastapi_v0_25_dubbing_workflow_returns_candidates_and_streams_role_events(
    monkeypatch, tmp_path
):
    """Covers v0.25 API wiring for role analysis pause and streamed role-selection updates."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import _create_dubbing_workflow, create_app
    from backend.app.domain.dubbing_workflow import (
        LangChainRoleAnalysisSkill,
        RoleAnalysisCandidate,
        RoleSelectionResult,
    )

    selected_role_id = {"value": None}

    def fake_analyze_roles(self, **kwargs):
        assert kwargs["chapter_id"] == "chapter-0001"
        assert self.provider["base_url"] == "https://api.example.test/v1"
        assert self.provider["model"] == "openai-compatible-test-model"
        return [
            RoleAnalysisCandidate(
                name="旁白",
                aliases=[],
                gender=None,
                profile="叙述者",
                voice_direction="沉稳清晰",
                evidence=["旁白第一段。"],
                confidence=0.9,
                needs_human_review=True,
            )
        ]

    def fake_needs_segmentation(self, **kwargs):
        return False

    def fake_choose_role(self, **kwargs):
        return RoleSelectionResult(
            role_id=selected_role_id["value"],
            speaker_name="旁白",
            confidence=0.88,
            needs_human_review=False,
            reason="叙述文本",
        )

    def fake_choose_roles_batch(self, **kwargs):
        assert len(kwargs["statements"]) == 1
        return {
            "items": [
                {
                    "statement_id": kwargs["statements"][0]["statement_id"],
                    "action": "select_role",
                    "role_id": selected_role_id["value"],
                    "confidence": 0.88,
                    "reason": "叙述文本",
                    "evidence": "旁白",
                }
            ]
        }

    monkeypatch.setattr(LangChainRoleAnalysisSkill, "analyze_roles", fake_analyze_roles)
    monkeypatch.setattr(LangChainRoleAnalysisSkill, "needs_segmentation", fake_needs_segmentation)
    monkeypatch.setattr(LangChainRoleAnalysisSkill, "choose_role", fake_choose_role)
    monkeypatch.setattr(LangChainRoleAnalysisSkill, "choose_roles_batch", fake_choose_roles_batch)
    monkeypatch.setattr("backend.app.api.app.OUTPUT_VOICE_RESOURCE_DIR", tmp_path / "voices")
    monkeypatch.setattr(
        "backend.app.api.app.synthesize_voice_design_qwen3",
        lambda _request, *, output_path, service_base_url=None: write_valid_wav(output_path),
    )

    client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
    config_response = client.patch(
        "/api/v1/model-config",
        json={
            "text_model": {
                "base_url": "https://api.example.test/v1",
                "model": "openai-compatible-test-model",
            },
        },
    )
    assert config_response.status_code == 200
    workflow = _create_dubbing_workflow(client.app)
    assert workflow.role_skill.provider["base_url"] == "https://api.example.test/v1"
    assert workflow.segmentation_service.provider["base_url"] == "https://api.example.test/v1"
    sync = client.put(
        "/api/v1/chapters/chapter-0001/paragraphs",
        json={
            "title": "第一章",
            "paragraphs": [{"paragraph_id": "p-0001", "text": "旁白第一段。"}],
            "confirm": False,
        },
    )
    assert sync.status_code == 200

    started = client.post("/api/v1/chapters/chapter-0001/agent-runs", json={})
    assert started.status_code == 200
    start_data = started.json()
    assert start_data["status"] == "waiting_for_roles"
    assert start_data["role_candidates"][0]["name"] == "旁白"
    assert "自动添加/更新角色" in start_data["message"]
    auto_role_id = start_data["roles"][0]["role_id"]
    selected_role_id["value"] = auto_role_id

    streamed = client.post(
        f"/api/v1/agent-runs/{start_data['thread_id']}/events",
        json={"roles": start_data["roles"], "utterances_by_paragraph": {}},
    )
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    frames = [frame for frame in streamed.text.split("\n\n") if frame.strip()]
    events = []
    for frame in frames:
        fields = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append(
            {"id": int(fields["id"]), "event": fields["event"], "data": json.loads(fields["data"])}
        )
    assert events[0]["id"] == 1
    assert events[0]["event"] == "role_selected"
    assert events[0]["data"]["utterance_id"] == "p-0001-u-001"
    assert events[0]["data"]["speaker_role_id"] == auto_role_id
    assert events[-1]["event"] == "completed"
    assert (
        events[-1]["data"]["utterances_by_paragraph"]["p-0001"][0]["speaker_role_id"]
        == auto_role_id
    )

    resumed = client.post(
        f"/api/v1/agent-runs/{start_data['thread_id']}/events",
        headers={"Last-Event-ID": "1"},
        json={"roles": start_data["roles"], "utterances_by_paragraph": {}},
    )
    assert "id: 1\n" not in resumed.text
    assert f"id: {events[-1]['id']}\n" in resumed.text


def test_fastapi_segmentation_requires_confirmation_and_real_provider_key(monkeypatch):
    """Covers AC-FLOW-05, AC-FLOW-06, AC-LLM-01, and AC-REAL-02."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app

    monkeypatch.delenv("SHUYI_TEXT_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
    parse_response = client.post(
        "/api/v1/books/parse",
        json={"text": "第一章 初遇\n他说：“你好。”"},
    )
    assert parse_response.status_code == 200

    blocked = client.post("/api/v1/paragraphs/p-0001/segment", json={})
    assert blocked.status_code == 409
    assert "确认段落" in blocked.json()["detail"]

    confirm_response = client.patch("/api/v1/paragraphs/p-0001", json={"confirm_all": True})
    assert confirm_response.status_code == 200
    assert confirm_response.json()["can_segment"] is True

    missing_key = client.post("/api/v1/paragraphs/p-0001/segment", json={})
    assert missing_key.status_code == 503
    assert "SHUYI_TEXT_MODEL_API_KEY" in missing_key.json()["detail"]


def test_fastapi_role_patch_persists_for_later_reads():
    """Covers AC-FLOW-08 and backend persistence for edited role cards."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app

    client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
    _post_test_role(client)
    response = client.patch(
        "/api/v1/characters/narrator",
        json={
            "name": "旁白改",
            "reference_audio_path": "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
            "reference_text": "齐心协力",
        },
    )
    assert response.status_code == 200
    assert {"value": "narrator", "label": "旁白改"} in response.json()["role_options"]

    roles_response = client.get("/api/v1/characters")
    assert roles_response.status_code == 200
    narrator = next(
        role for role in roles_response.json()["roles"] if role["role_id"] == "narrator"
    )
    assert narrator["name"] == "旁白改"
    assert narrator["reference_audio_path"] is None
    assert narrator["reference_text"] == "齐心协力"


def test_fastapi_segmentation_uses_provider_and_repairs_once(monkeypatch):
    """Covers AC-LLM-02, AC-LLM-05, and end-to-end API repair behavior."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app
    from backend.app.domain.ai_segmentation_agent import LangChainSegmentationSkill

    monkeypatch.setenv("SHUYI_TEXT_MODEL_API_KEY", "test-token")

    def fake_segment(self, *, chapter_title, paragraph_id, paragraph_text, known_roles):
        assert chapter_title == "第一章 初遇"
        return f"""```json
{{
  "paragraph_id": "{paragraph_id}",
  "utterances": [
    {{
      "utterance_id": "{paragraph_id}-u-001",
      "speaker_name": "旁白",
      "speaker_role_id": "narrator",
      "voice_mode": "voice_cloning",
      "text": "{paragraph_text}",
      "emotion": "neutral",
      "speed": 1.0,
      "volume": 1.0,
      "design_prompt": null,
      "confidence": 0.9,
      "needs_human_review": false
    }}
  ]
}}
```"""

    with patch.object(LangChainSegmentationSkill, "segment", fake_segment):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        assert (
            client.post(
                "/api/v1/books/parse", json={"text": "第一章 初遇\n他说：“你好。”"}
            ).status_code
            == 200
        )
        assert (
            client.patch("/api/v1/paragraphs/p-0001", json={"confirm_all": True}).status_code == 200
        )
        response = client.post("/api/v1/paragraphs/p-0001/segment", json={})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["repaired"] is True
    assert data["raw_output"].startswith("```json")
    assert data["utterances"][0]["text"] == "他说：“你好。”"


def write_valid_wav(
    path: Path, *, duration_seconds: float = 0.75, sample_rate: int = 16000
) -> None:
    frame_count = int(duration_seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)


def install_python_multipart_stub(monkeypatch) -> None:
    python_multipart = types.ModuleType("python_multipart")
    python_multipart.__version__ = "0.0.20"
    python_multipart.__all__ = []
    python_multipart_parser = types.ModuleType("python_multipart.multipart")
    python_multipart_parser.parse_options_header = lambda value: (value, {})
    monkeypatch.setitem(sys.modules, "python_multipart", python_multipart)
    monkeypatch.setitem(sys.modules, "python_multipart.multipart", python_multipart_parser)


def test_wav_duration_validation_rejects_invalid_and_short_audio(tmp_path):
    """Covers AC-AUDIO-06 regression behavior for decode and duration checks."""
    valid = tmp_path / "valid.wav"
    write_valid_wav(valid, duration_seconds=0.75)
    assert validate_wav_duration(valid) == 0.75

    short = tmp_path / "short.wav"
    write_valid_wav(short, duration_seconds=0.25)
    with pytest.raises(TTSServiceError, match="时长"):
        validate_wav_duration(short)

    invalid = tmp_path / "invalid.wav"
    invalid.write_bytes(b"not-a-wave")
    with pytest.raises(TTSServiceError, match="可解码的 WAV"):
        validate_wav_duration(invalid)


def test_fastapi_tts_endpoint_invokes_local_service_and_returns_audio_url(tmp_path):
    """Covers AC-AUDIO-06 and AC-AUDIO-07 API behavior with a local TTS substitute."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    calls = []

    def fake_synthesize(request, *, output_path, service_base_url=None):
        calls.append({"request": request, "output_path": output_path})
        write_valid_wav(output_path)
        return 0.75

    with (
        patch.object(app_module, "OUTPUT_AUDIO_DIR", tmp_path),
        patch.object(app_module, "synthesize_local_qwen3", fake_synthesize),
    ):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        reference_audio = tmp_path / "narrator-reference.wav"
        write_valid_wav(reference_audio)
        _post_test_role(client, reference_audio_path=reference_audio)
        response = client.post(
            "/api/v1/dubbing-segments/p-0001-u-001/dubbing-jobs",
            json={
                "role_id": "narrator",
                "text": "待合成文本",
                "voice_mode": "voice_cloning",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["voice_job"]["status"] == "succeeded"
    assert data["voice_job"]["utterance_id"] == "p-0001-u-001"
    assert data["voice_job"]["provider"] == "local-qwen3-tts"
    assert data["audio_url"] == "/api/v1/downloads/audio/vj-0001.wav"
    assert data["duration_seconds"] == 0.75
    assert calls[0]["request"]["input"] == "待合成文本"


def test_fastapi_v0_21_speech_synthesis_does_not_block_voice_resource_reads(tmp_path):
    """Covers v0.21: one running TTS job must not block already playable resources."""
    pytest.importorskip("fastapi")
    httpx = pytest.importorskip("httpx")

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    reference_audio = tmp_path / "reference.wav"
    write_valid_wav(reference_audio)

    def slow_synthesize(request, *, output_path, service_base_url=None):
        time.sleep(0.2)
        write_valid_wav(output_path)
        return 0.75

    async def scenario():
        with (
            patch.object(app_module, "OUTPUT_AUDIO_DIR", tmp_path / "audio"),
            patch.object(app_module, "OUTPUT_VOICE_RESOURCE_DIR", tmp_path / "voices"),
            patch.object(app_module, "synthesize_local_qwen3", slow_synthesize),
        ):
            app = create_app()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Authorization": "Bearer test-v0-4-token"},
            ) as client:
                create_voice = await client.post(
                    "/api/v1/voice-profiles",
                    json={
                        "voice_id": "voice-concurrent",
                        "name": "并发测试音色",
                        "description": "用于并发生成测试",
                        "reference_text": "参考文本",
                        "reference_audio_path": str(reference_audio),
                    },
                )
                assert create_voice.status_code == 200
                await _apost_test_role(
                    client,
                    reference_audio_path=reference_audio,
                    voice_resource_id="voice-concurrent",
                )

                started_at = time.perf_counter()
                speech_task = asyncio.create_task(
                    client.post(
                        "/api/v1/dubbing-segments/p-0001-u-001/dubbing-jobs",
                        json={
                            "role_id": "narrator",
                            "voice_resource_id": "voice-concurrent",
                            "text": "第一条正在生成的文本",
                            "voice_mode": "voice_cloning",
                        },
                    )
                )
                await asyncio.sleep(0.02)
                elapsed_before_read = time.perf_counter() - started_at
                voices_response = await client.get("/api/v1/voice-profiles")
                speech_response = await speech_task
                return elapsed_before_read, voices_response, speech_response

    elapsed, voices_response, speech_response = asyncio.run(scenario())

    assert elapsed < 0.12
    assert voices_response.status_code == 200
    assert speech_response.status_code == 200


def test_qwen3_tts_server_reuses_voice_clone_prompt_for_same_reference(tmp_path, monkeypatch):
    """Covers v0.12 reusable prompt behavior in the local Base model service."""
    install_python_multipart_stub(monkeypatch)

    from backend.tts import qwen3_tts_server as server

    reference = tmp_path / "reference.wav"
    write_valid_wav(reference)
    audio_bytes = reference.read_bytes()

    class FakeCloneModel:
        def __init__(self):
            self.prompt_calls = 0
            self.generate_calls = []

        def create_voice_clone_prompt(self, *, ref_audio, ref_text, x_vector_only=False):
            self.prompt_calls += 1
            assert Path(ref_audio).exists()
            assert ref_text == "这是一段短参考音频。"
            assert x_vector_only is False
            return {"cached": self.prompt_calls}

        def generate_voice_clone(self, **kwargs):
            self.generate_calls.append(kwargs)
            return ["wav"], 24000

    model = FakeCloneModel()
    server.voice_clone_prompt_cache.clear()

    first = server.generate_voice_clone_with_reusable_prompt(
        model,
        text="第一句目标台词",
        language="Auto",
        reference_path=str(reference),
        reference_audio=audio_bytes,
        reusable_prompt="这是一段短参考音频。",
        x_vector_only=False,
    )
    second = server.generate_voice_clone_with_reusable_prompt(
        model,
        text="第二句目标台词",
        language="Auto",
        reference_path=str(reference),
        reference_audio=audio_bytes,
        reusable_prompt="这是一段短参考音频。",
        x_vector_only=False,
    )

    assert first == (["wav"], 24000)
    assert second == (["wav"], 24000)
    assert model.prompt_calls == 1
    assert len(model.generate_calls) == 2
    for call in model.generate_calls:
        assert call["language"] == "Auto"
        assert call["voice_clone_prompt"] == {"cached": 1}
        assert "ref_audio" not in call
        assert "ref_text" not in call


def test_qwen3_tts_server_supports_x_vector_only_mode_prompt_argument(tmp_path, monkeypatch):
    """Covers v0.23 Qwen3 create_voice_clone_prompt argument name used by the local runtime."""
    install_python_multipart_stub(monkeypatch)

    from backend.tts import qwen3_tts_server as server

    reference = tmp_path / "reference.wav"
    write_valid_wav(reference)
    audio_bytes = reference.read_bytes()

    class FakeCloneModel:
        def __init__(self):
            self.x_vector_only_mode = None

        def create_voice_clone_prompt(self, *, ref_audio, ref_text, x_vector_only_mode=False):
            assert Path(ref_audio).exists()
            assert ref_text == "这是一段短参考音频。"
            self.x_vector_only_mode = x_vector_only_mode
            return {"cached": "modern"}

        def generate_voice_clone(self, **kwargs):
            return [kwargs["voice_clone_prompt"]], 24000

    model = FakeCloneModel()
    server.voice_clone_prompt_cache.clear()

    result = server.generate_voice_clone_with_reusable_prompt(
        model,
        text="目标台词",
        language="Auto",
        reference_path=str(reference),
        reference_audio=audio_bytes,
        reusable_prompt="这是一段短参考音频。",
        x_vector_only=True,
    )

    assert result == ([{"cached": "modern"}], 24000)
    assert model.x_vector_only_mode is True


def test_qwen3_tts_server_json_voice_clone_uses_reference_audio_suffix(monkeypatch):
    """Covers v0.23 JSON voice-clone temp file suffix preservation for MP3 references."""
    install_python_multipart_stub(monkeypatch)

    from backend.tts import qwen3_tts_server as server

    captured = {}

    def fake_generate_voice_clone(model, **kwargs):
        captured["reference_path"] = kwargs["reference_path"]
        captured["reference_audio"] = kwargs["reference_audio"]
        return ["wav"], 24000

    def fake_encode_audio_response(wav, sr, response_format):
        return {"wav": wav, "sr": sr, "response_format": response_format}

    monkeypatch.setattr(
        server, "generate_voice_clone_with_reusable_prompt", fake_generate_voice_clone
    )
    monkeypatch.setattr(server, "encode_audio_response", fake_encode_audio_response)

    response = asyncio.run(
        server.speech_json(
            {
                "input": "目标生成台词",
                "audio_sample": base64.b64encode(b"ID3 fake mp3 bytes").decode("ascii"),
                "audio_sample_suffix": ".mp3",
                "ref_text": "参考文本",
                "language": "Auto",
                "response_format": "wav",
            }
        )
    )

    assert response == {"wav": "wav", "sr": 24000, "response_format": "wav"}
    assert Path(captured["reference_path"]).suffix == ".mp3"
    assert captured["reference_audio"] == b"ID3 fake mp3 bytes"


def test_fastapi_tts_endpoint_returns_substitute_audio_when_local_service_is_down(tmp_path):
    """Covers v0.13 graceful audio generation fallback for a missing local TTS service."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    def unavailable_service(request, *, output_path, service_base_url=None):
        raise TTSServiceError(
            "本地 Qwen3-TTS 请求失败：<urlopen error [Errno 61] Connection refused>"
        )

    with (
        patch.object(app_module, "OUTPUT_AUDIO_DIR", tmp_path),
        patch.object(app_module, "synthesize_local_qwen3", unavailable_service),
    ):
        client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
        reference_audio = tmp_path / "narrator-reference.wav"
        write_valid_wav(reference_audio)
        _post_test_role(client, reference_audio_path=reference_audio)
        response = client.post(
            "/api/v1/dubbing-segments/p-0001-u-001/dubbing-jobs",
            json={
                "role_id": "narrator",
                "text": "待合成文本",
                "voice_mode": "voice_cloning",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["voice_job"]["status"] == "substitute"
    assert "Qwen3-TTS" in data["voice_job"]["error"]
    assert data["audio_url"] == "/api/v1/downloads/audio/vj-0001.wav"
    assert validate_wav_duration(tmp_path / "vj-0001.wav") == 0.75
