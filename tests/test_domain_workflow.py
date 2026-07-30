import json
import sys
import types
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.domain.audio import (
    TTSServiceError,
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
from backend.app.domain.roles import RoleCollection, default_role_cards
from backend.app.domain.segmentation import validate_segmentation_result
from backend.app.domain.voices import (
    VoiceResourceCollection,
    default_voice_resources,
    generated_voice_content,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_NOVEL = ROOT / "assets/samples/novels/hongloumeng_pg24264_excerpt.txt"
REAL_SAMPLE_ROOT = Path("/Users/gaojing/Downloads/真实测试样本")
REAL_NOVEL = REAL_SAMPLE_ROOT / "小说/这个地下城长蘑菇了.txt"
REAL_VOICE_ROOT = REAL_SAMPLE_ROOT / "音频"


def test_parse_sample_novel_into_chapters_and_paragraph_workbench_gate():
    """Covers AC-FLOW-02, AC-FLOW-03, AC-FLOW-04, AC-FLOW-05, AC-FLOW-06."""
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
    assert first_paragraph.paragraph_id not in [p.paragraph_id for p in workbench.visible_paragraphs]
    assert workbench.can_segment is False

    workbench.confirm_paragraphs()
    assert workbench.can_segment is True


def test_default_roles_and_role_options_sync_to_utterance_selectors():
    """Covers AC-FLOW-08, AC-ROLE-01, AC-ROLE-02, and v0.11 voice resources."""
    roles = default_role_cards()
    assert [role.name for role in roles] == ["旁白", "年轻男", "御姐音"]
    assert {role.voice_mode for role in roles} <= {"voice_cloning", "voice_design"}

    for role in roles:
        assert role.role_id
        assert role.name
        assert role.description
        assert role.voice_resource_id
        assert "功能烟测占位" not in role.description
        if role.voice_mode == "voice_cloning":
            assert role.reference_audio_path
            assert role.reference_text

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
    assert {option["value"] for option in options} >= {"narrator", "male_lead", "female_lead", "villain"}
    assert next(option for option in options if option["value"] == "villain")["label"] == "反派"


def test_v0_11_numeric_heading_real_sample_splits_into_chapters():
    """Covers v0.11 real novel parsing for numeric headings such as `1.标题`."""
    if not REAL_NOVEL.exists():
        pytest.skip(f"real sample novel not found: {REAL_NOVEL}")

    chapters = parse_novel_text(REAL_NOVEL.read_text(encoding="utf-8"))

    assert len(chapters) >= 30
    assert chapters[0].chapter_id == "chapter-0001"
    assert chapters[0].title == "1.变成蘑菇的公爵千金"
    assert chapters[1].title == "2.蘑菇园来了个外乡菇"
    assert chapters[0].title != "未分章正文"
    assert "伊南娜" in chapters[0].body


def test_v0_11_voice_resources_load_real_samples_and_support_crud():
    """Covers v0.11 voice resource library data behavior."""
    resources = default_voice_resources(REAL_VOICE_ROOT if REAL_VOICE_ROOT.exists() else None)
    collection = VoiceResourceCollection(resources)
    names = {resource.name for resource in collection.list()}

    if REAL_VOICE_ROOT.exists():
        assert {"年轻男", "御姐音", "播音腔女", "男声旁白"} <= names
        young_male = next(resource for resource in collection.list() if resource.name == "年轻男")
        assert young_male.reference_audio_path.endswith("年轻男.mp3")
        assert "光柱最终落在" in young_male.reference_text

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
    """Covers v0.11 generated voice resource boundary without claiming real TTS quality."""
    content = generated_voice_content("冷静旁白", "沉稳、克制、叙事感强")

    assert "冷静旁白" in content
    assert "沉稳、克制、叙事感强" in content
    assert len(content) > 20


def test_provider_registry_preserves_default_llm_boundaries():
    """Covers AC-LLM-01 and provider boundary from architecture contract."""
    registry = default_provider_registry()

    siliconflow = registry["siliconflow-qwen3-8b"]
    assert siliconflow["kind"] == "chat_completions"
    assert siliconflow["base_url"] == "https://api.siliconflow.cn/v1"
    assert siliconflow["model"] == "Qwen/Qwen3-8B"
    assert siliconflow["api_key_env"] == "SILICONFLOW_API_KEY"
    assert siliconflow["max_tokens"] == 768
    assert siliconflow["extra_body"] == {"enable_thinking": False}

    deepseek = registry["deepseek-harness"]
    assert deepseek["base_url"] == "https://api.deepseek.com"
    assert deepseek["model"] == "deepseek-v4-flash"
    assert deepseek["api_key_env"] == "DEEPSEEK_API_KEY"


def test_llm_segmentation_client_builds_openai_compatible_request():
    """Covers AC-LLM-01, AC-LLM-02, and provider registry API boundary."""
    provider = default_provider_registry()["siliconflow-qwen3-8b"]
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
        api_key_lookup=lambda name: "test-token" if name == "SILICONFLOW_API_KEY" else None,
        http_post=fake_http_post,
    )
    raw_output = client.segment(
        chapter_title="第一章 初遇",
        paragraph_id="p-0001",
        paragraph_text="他说：“你好。”",
        known_roles=[{"role_id": "narrator", "name": "旁白", "description": "叙述者"}],
    )

    assert raw_output == '{"paragraph_id":"p-0001","utterances":[]}'
    assert captured["url"] == "https://api.siliconflow.cn/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["payload"]["model"] == "Qwen/Qwen3-8B"
    assert captured["payload"]["enable_thinking"] is False
    assert captured["payload"]["max_tokens"] == 768
    assert "extra_body" not in captured["payload"]
    assert captured["payload"]["messages"] == messages


def test_v0_14_segmentation_prompt_targets_speaker_units_not_mechanical_sentences():
    """Covers v0.14 speaker-unit segmentation requirements for Qwen/Qwen3-8B."""
    paragraph = "“别笑了，引来魔物就麻烦了。”佩罗不耐烦地打断了笑声，“就这了，把她放下来。”"
    messages = build_segmentation_messages(
        chapter_title="1.变成蘑菇的公爵千金",
        paragraph_id="p-0001",
        paragraph_text=paragraph,
        known_roles=[{"role_id": "narrator", "name": "旁白"}, {"role_id": "peruo", "name": "佩罗"}],
    )
    prompt = messages[-1]["content"]

    assert "以说话人/角色为单位" in prompt
    assert "不是按句号机械拆分" in prompt
    assert "双引号" in prompt
    assert "“别笑了，引来魔物就麻烦了。”" in prompt
    assert "佩罗不耐烦地打断了笑声" in prompt
    assert "“就这了，把她放下来。”" in prompt
    assert "Qwen/Qwen3-8B" in prompt


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
                    "design_prompt": "年轻男性，自然说话",
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
    broken_raw = json.dumps({"paragraph_id": "p-0001", "utterances": [utterance]}, ensure_ascii=False)
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


def test_tts_request_validation_and_voice_job_traceability():
    """Covers AC-ROLE-03, AC-ROLE-04, and AC-AUDIO-07."""
    roles = RoleCollection(default_role_cards())
    narrator = roles.get("narrator")
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
    with pytest.raises(ValueError, match="reference audio"):
        build_tts_request(utterance, missing_reference)

    design_role = roles.get("female_lead").with_updates(
        voice_mode="voice_design",
        design_prompt=None,
        reference_audio_path=None,
        reference_text=None,
    )
    with pytest.raises(ValueError, match="design prompt"):
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

    role = RoleCollection(default_role_cards()).get("narrator").with_updates(
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


def test_fastapi_app_exposes_v0_11_resource_boundaries():
    """Covers architecture API boundary for the v0.11 manual workbench."""
    pytest.importorskip("fastapi")
    from backend.app.api.app import create_app

    app = create_app()
    routes = {}
    for route in app.routes:
        if hasattr(route, "methods"):
            routes.setdefault(route.path, set()).update(route.methods)

    expected = [
        ("/api/novels/parse", "POST"),
        ("/api/chapters", "GET"),
        ("/api/chapters/{chapter_id}", "GET"),
        ("/api/chapters/{chapter_id}/paragraphs", "PUT"),
        ("/api/paragraphs/{paragraph_id}", "PATCH"),
        ("/api/paragraphs/{paragraph_id}/segment", "POST"),
        ("/api/roles", "GET"),
        ("/api/roles", "POST"),
        ("/api/roles/{role_id}", "PATCH"),
        ("/api/voice-resources", "GET"),
        ("/api/voice-resources", "POST"),
        ("/api/voice-resources/generate", "POST"),
        ("/api/voice-resources/reference-audio", "POST"),
        ("/api/voice-resources/{voice_id}", "PATCH"),
        ("/api/voice-resources/{voice_id}", "DELETE"),
        ("/api/voice-resources/{voice_id}/audio", "GET"),
        ("/api/model-config", "GET"),
        ("/api/model-config", "PATCH"),
        ("/api/model-config/llm/test", "POST"),
        ("/api/model-config/tts/start", "POST"),
        ("/api/utterances/{utterance_id}/speech", "POST"),
    ]
    for path, method in expected:
        assert method in routes[path]


def test_fastapi_v0_11_voice_resource_crud_and_role_voice_sync():
    """Covers v0.11 voice resource API and role selection synchronization."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app

    client = TestClient(create_app())
    list_response = client.get("/api/voice-resources")
    assert list_response.status_code == 200
    assert list_response.json()["voices"]

    create_response = client.post(
        "/api/voice-resources",
        json={
            "name": "接口测试音色",
            "description": "明亮、自然、适合少年角色",
            "reference_text": "接口测试语音内容。",
            "reference_audio_path": "outputs/audio/api-test.wav",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()["voice"]
    assert created["voice_id"].startswith("voice-")
    assert created["name"] == "接口测试音色"

    role_response = client.patch(
        "/api/roles/narrator",
        json={
            "name": "旁白",
            "voice_resource_id": created["voice_id"],
        },
    )
    assert role_response.status_code == 200
    role = role_response.json()["role"]
    assert role["voice_resource_id"] == created["voice_id"]
    assert role["reference_audio_path"] == "outputs/audio/api-test.wav"
    assert role["reference_text"] == "接口测试语音内容。"

    update_response = client.patch(
        f"/api/voice-resources/{created['voice_id']}",
        json={"description": "已通过接口修改"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["voice"]["description"] == "已通过接口修改"

    delete_response = client.delete(f"/api/voice-resources/{created['voice_id']}")
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
        calls.append({"request": request, "output_path": output_path, "service_base_url": service_base_url})
        write_valid_wav(output_path)
        return 0.75

    with (
        patch.object(app_module, "OUTPUT_AUDIO_DIR", tmp_path),
        patch.object(app_module, "synthesize_voice_design_qwen3", fake_voice_design),
    ):
        client = TestClient(create_app())
        before_count = len(client.get("/api/voice-resources").json()["voices"])
        generated = client.post(
            "/api/voice-resources/generate",
            json={
                "name": "生成旁白",
                "description": "沉稳、叙事、颗粒感轻",
                "reference_text": "这是一段用于试听新音色的语音。",
            },
        )
        after_generate_count = len(client.get("/api/voice-resources").json()["voices"])

        assert generated.status_code == 200
        data = generated.json()
        voice = data["voice"]
        assert voice["generated"] is True
        assert voice["voice_id"].startswith("preview-")
        assert voice["reference_text"] == "这是一段用于试听新音色的语音。"
        assert voice["reference_audio_path"].endswith(".wav")
        assert data["audio_url"].startswith("/outputs/audio/")
        assert data["generation_status"] == "succeeded"
        assert "VoiceDesign" in data["generation_note"]
        assert calls[0]["request"]["input"] == "这是一段用于试听新音色的语音。"
        assert calls[0]["request"]["instruct"] == "沉稳、叙事、颗粒感轻"
        assert calls[0]["request"]["language"] == "Auto"
        assert before_count == after_generate_count

        saved = client.post(
            "/api/voice-resources",
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


def test_fastapi_v0_141_generated_voice_substitute_explains_required_model(tmp_path):
    """Covers v0.141 fallback explanation when VoiceDesign is unavailable."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    def unavailable_voice_design(request, *, output_path, service_base_url=None):
        raise TTSServiceError("voice design endpoint unavailable")

    with (
        patch.object(app_module, "OUTPUT_AUDIO_DIR", tmp_path),
        patch.object(app_module, "synthesize_voice_design_qwen3", unavailable_voice_design),
    ):
        client = TestClient(create_app())
        generated = client.post(
            "/api/voice-resources/generate",
            json={
                "name": "生成旁白",
                "description": "沉稳、叙事、颗粒感轻",
                "reference_text": "这是一段用于试听新音色的语音。",
            },
        )

    assert generated.status_code == 200
    data = generated.json()
    assert data["generation_status"] == "substitute"
    assert "没有成功调用 VoiceDesign 模型" in data["generation_note"]
    assert "Qwen3-TTS-12Hz-1.7B-VoiceDesign" in data["model_requirement"]
    assert validate_wav_duration(Path(data["voice"]["reference_audio_path"])) == 0.75


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
        client = TestClient(create_app())
        response = client.post(
            "/api/voice-resources/reference-audio",
            json={
                "filename": "角色 试听.wav",
                "data_base64": "UklGRgAAAAA=",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["reference_audio_path"].startswith(str(tmp_path))
    assert data["filename"].endswith(".wav")
    assert Path(data["reference_audio_path"]).exists()


def test_fastapi_v0_14_model_config_boundaries_and_feedback_endpoints(monkeypatch):
    """Covers v0.14 split model-config save/test/start API behavior."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    client = TestClient(create_app())

    config_response = client.get("/api/model-config")
    assert config_response.status_code == 200
    config = config_response.json()["config"]
    assert config["llm"]["base_url"] == "https://api.siliconflow.cn/v1"
    assert config["llm"]["model"] == "Qwen/Qwen3-8B"
    assert config["llm"]["api_key"] == ""
    assert config["tts"]["base_url"] == "http://127.0.0.1:7811"
    assert config["tts"]["model_path"] == app_module.DEFAULT_BASE_MODEL_PATH
    assert config["tts"]["voice_design_model_path"] == app_module.DEFAULT_VOICE_DESIGN_MODEL_PATH

    remote_save = client.patch(
        "/api/model-config",
        json={
            "llm": {
                "base_url": "https://api.example.test/v1",
                "model": "remote-test-model",
                "api_key": "test-placeholder-key",
            },
        },
    )
    assert remote_save.status_code == 200
    updated = remote_save.json()["config"]
    assert updated["llm"]["base_url"] == "https://api.example.test/v1"
    assert updated["llm"]["model"] == "remote-test-model"
    assert updated["llm"]["api_key"] == "test-placeholder-key"

    local_save = client.patch(
        "/api/model-config",
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

    monkeypatch.setattr(app_module.urllib.request, "urlopen", lambda request, timeout=10: FakeResponse())
    test_link = client.post("/api/model-config/llm/test", json={})
    assert test_link.status_code == 200
    assert test_link.json()["ok"] is True
    assert "远端模型连接成功" in test_link.json()["message"]

    calls = []

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    monkeypatch.setattr(app_module.subprocess, "Popen", lambda *args, **kwargs: calls.append(args) or FakeProcess())
    start = client.post("/api/model-config/tts/start", json={})
    assert start.status_code == 200
    assert start.json()["ok"] is True
    assert "启动" in start.json()["message"]
    assert calls
    command = calls[0][0]
    assert "--model-path" in command
    assert "--voice-design-model-path" in command
    assert "/models/qwen3-tts" in command
    assert "/models/qwen3-tts-voice-design" in command


def test_fastapi_v0_14_syncs_current_local_paragraphs_before_confirmation():
    """Covers v0.14 fix for stale backend paragraph state after local edits/deletes."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app

    client = TestClient(create_app())
    response = client.put(
        "/api/chapters/chapter-0001/paragraphs",
        json={
            "title": "1.变成蘑菇的公爵千金",
            "paragraphs": [
                {
                    "paragraph_id": "p-0002",
                    "text": "一醒来就发现自己被装麻袋了的伊南娜竭力扭动身体。",
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
    missing_key = client.post("/api/paragraphs/p-0002/segment", json={})
    assert missing_key.status_code == 503
    assert "paragraph not found" not in missing_key.text


def test_fastapi_segmentation_requires_confirmation_and_real_provider_key(monkeypatch):
    """Covers AC-FLOW-05, AC-FLOW-06, AC-LLM-01, and AC-REAL-02."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app

    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    client = TestClient(create_app())
    parse_response = client.post(
        "/api/novels/parse",
        json={"text": "第一章 初遇\n他说：“你好。”"},
    )
    assert parse_response.status_code == 200

    blocked = client.post("/api/paragraphs/p-0001/segment", json={})
    assert blocked.status_code == 409
    assert "confirmed" in blocked.json()["detail"]

    confirm_response = client.patch("/api/paragraphs/p-0001", json={"confirm_all": True})
    assert confirm_response.status_code == 200
    assert confirm_response.json()["can_segment"] is True

    missing_key = client.post("/api/paragraphs/p-0001/segment", json={})
    assert missing_key.status_code == 503
    assert "SILICONFLOW_API_KEY" in missing_key.json()["detail"]


def test_fastapi_role_patch_persists_for_later_reads():
    """Covers AC-FLOW-08 and backend persistence for edited role cards."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app

    client = TestClient(create_app())
    response = client.patch(
        "/api/roles/narrator",
        json={
            "name": "旁白改",
            "reference_audio_path": "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
            "reference_text": "齐心协力",
        },
    )
    assert response.status_code == 200
    assert {"value": "narrator", "label": "旁白改"} in response.json()["role_options"]

    roles_response = client.get("/api/roles")
    assert roles_response.status_code == 200
    narrator = next(role for role in roles_response.json()["roles"] if role["role_id"] == "narrator")
    assert narrator["name"] == "旁白改"
    assert narrator["reference_audio_path"].endswith("cmn_qixinxieli_canonni_cc0.wav")
    assert narrator["reference_text"] == "齐心协力"


def test_fastapi_segmentation_uses_provider_and_repairs_once(monkeypatch):
    """Covers AC-LLM-02, AC-LLM-05, and end-to-end API repair behavior."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api.app import create_app
    from backend.app.domain.llm import OpenAICompatibleSegmentationClient

    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-token")

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

    with patch.object(OpenAICompatibleSegmentationClient, "segment", fake_segment):
        client = TestClient(create_app())
        assert client.post("/api/novels/parse", json={"text": "第一章 初遇\n他说：“你好。”"}).status_code == 200
        assert client.patch("/api/paragraphs/p-0001", json={"confirm_all": True}).status_code == 200
        response = client.post("/api/paragraphs/p-0001/segment", json={})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["repaired"] is True
    assert data["raw_output"].startswith("```json")
    assert data["utterances"][0]["text"] == "他说：“你好。”"


def write_valid_wav(path: Path, *, duration_seconds: float = 0.75, sample_rate: int = 16000) -> None:
    frame_count = int(duration_seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)


def test_wav_duration_validation_rejects_invalid_and_short_audio(tmp_path):
    """Covers AC-AUDIO-06 regression behavior for decode and duration checks."""
    valid = tmp_path / "valid.wav"
    write_valid_wav(valid, duration_seconds=0.75)
    assert validate_wav_duration(valid) == 0.75

    short = tmp_path / "short.wav"
    write_valid_wav(short, duration_seconds=0.25)
    with pytest.raises(TTSServiceError, match="duration"):
        validate_wav_duration(short)

    invalid = tmp_path / "invalid.wav"
    invalid.write_bytes(b"not-a-wave")
    with pytest.raises(TTSServiceError, match="decodable wav"):
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
        client = TestClient(create_app())
        response = client.post(
            "/api/utterances/p-0001-u-001/speech",
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
    assert data["audio_url"] == "/outputs/audio/vj-0001.wav"
    assert data["duration_seconds"] == 0.75
    assert calls[0]["request"]["input"] == "待合成文本"


def test_qwen3_tts_server_reuses_voice_clone_prompt_for_same_reference(tmp_path, monkeypatch):
    """Covers v0.12 reusable prompt behavior in the local Base model service."""
    monkeypatch.setitem(sys.modules, "python_multipart", types.SimpleNamespace(__version__="0.0.20"))

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


def test_fastapi_tts_endpoint_returns_substitute_audio_when_local_service_is_down(tmp_path):
    """Covers v0.13 graceful audio generation fallback for a missing local TTS service."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app

    def unavailable_service(request, *, output_path, service_base_url=None):
        raise TTSServiceError("local Qwen3-TTS request failed: <urlopen error [Errno 61] Connection refused>")

    with (
        patch.object(app_module, "OUTPUT_AUDIO_DIR", tmp_path),
        patch.object(app_module, "synthesize_local_qwen3", unavailable_service),
    ):
        client = TestClient(create_app())
        response = client.post(
            "/api/utterances/p-0001-u-001/speech",
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
    assert data["audio_url"] == "/outputs/audio/vj-0001.wav"
    assert validate_wav_duration(tmp_path / "vj-0001.wav") == 0.75
