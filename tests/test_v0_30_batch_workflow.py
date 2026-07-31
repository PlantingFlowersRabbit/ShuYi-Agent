from __future__ import annotations

import json
from pathlib import Path


def _role(role_id: str, name: str, voice_resource_id: str = "voice-narrator") -> dict:
    return {
        "role_id": role_id,
        "name": name,
        "description": f"{name} description",
        "voice_mode": "voice_cloning",
        "reference_audio_path": "reference.wav",
        "reference_text": "参考文本",
        "design_prompt": None,
        "voice_resource_id": voice_resource_id,
    }


def _utterance(utterance_id: str, paragraph_id: str, text: str, role_id: str | None = None) -> dict:
    return {
        "utterance_id": utterance_id,
        "paragraph_id": paragraph_id,
        "speaker_name": "",
        "speaker_role_id": role_id,
        "voice_mode": "voice_cloning",
        "text": text,
        "emotion": "neutral",
        "speed": 1.0,
        "volume": 1.0,
        "design_prompt": None,
        "confidence": 0.0,
        "needs_human_review": True,
    }


def test_v0_30_batch_role_selection_preserves_existing_roles_and_uses_one_llm_call():
    """Covers v0.3.0 batch role selection and non-overwrite constraints."""
    from backend.app.domain.ai_one_click_workflow import BatchRoleSelectionService

    class FakeBatchSkill:
        def __init__(self):
            self.calls = []

        def choose_roles_batch(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "items": [
                    {
                        "statement_id": "p-0001-u-002",
                        "action": "select_role",
                        "role_id": "hero",
                        "confidence": 0.91,
                        "reason": "dialogue cue",
                        "evidence": "你好",
                    },
                    {
                        "statement_id": "p-0001-u-003",
                        "action": "select_role",
                        "role_id": "narrator",
                        "confidence": 0.86,
                        "reason": "narration",
                        "evidence": "她点头",
                    },
                ]
            }

    utterances_by_paragraph = {
        "p-0001": [
            _utterance("p-0001-u-001", "p-0001", "已有角色。", "narrator"),
            _utterance("p-0001-u-002", "p-0001", "“你好。”"),
            _utterance("p-0001-u-003", "p-0001", "她点头。"),
        ]
    }
    service = BatchRoleSelectionService(FakeBatchSkill(), batch_size=20)

    report = service.select_roles_for_statements_batch(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        paragraphs=[{"paragraph_id": "p-0001", "text": "已有角色。\n“你好。”\n她点头。"}],
        utterances_by_paragraph=utterances_by_paragraph,
        roles=[_role("narrator", "旁白"), _role("hero", "林清", "voice-hero")],
    )

    assert report.status == "completed"
    assert len(service.role_skill.calls) == 1
    sent_ids = [item["statement_id"] for item in service.role_skill.calls[0]["statements"]]
    assert sent_ids == ["p-0001-u-002", "p-0001-u-003"]
    assert utterances_by_paragraph["p-0001"][0]["speaker_role_id"] == "narrator"
    assert utterances_by_paragraph["p-0001"][1]["speaker_role_id"] == "hero"
    assert utterances_by_paragraph["p-0001"][2]["speaker_role_id"] == "narrator"
    assert report.success_count == 2
    assert report.skipped_count == 1


def test_v0_30_batch_role_selection_splits_ambiguous_paragraph_and_retries_blank_results():
    """Covers v0.3.0 needs_split fallback into existing AI statement segmentation."""
    from backend.app.domain.ai_one_click_workflow import BatchRoleSelectionService
    from backend.app.domain.segmentation import SegmentationValidationResult

    class FakeBatchSkill:
        def __init__(self):
            self.calls = 0

        def choose_roles_batch(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "items": [
                        {
                            "statement_id": "p-0002-u-001",
                            "action": "needs_split",
                            "role_id": None,
                            "confidence": 0.3,
                            "reason": "dialogue plus narration",
                            "evidence": "“走。”他说。",
                        }
                    ]
                }
            return {
                "items": [
                    {
                        "statement_id": "p-0002-u-001",
                        "action": "select_role",
                        "role_id": "hero",
                        "confidence": 0.9,
                        "reason": "quoted speech",
                        "evidence": "走",
                    },
                    {
                        "statement_id": "p-0002-u-002",
                        "action": "select_role",
                        "role_id": "narrator",
                        "confidence": 0.85,
                        "reason": "narration",
                        "evidence": "他说",
                    },
                ]
            }

    class FakeSegmentationService:
        def __init__(self):
            self.calls = []

        def segment_paragraph(self, *, paragraph_id, **kwargs):
            self.calls.append(paragraph_id)
            return SegmentationValidationResult(
                ok=True,
                paragraph_id=paragraph_id,
                utterances=[
                    _utterance("p-0002-u-001", "p-0002", "“走。”"),
                    _utterance("p-0002-u-002", "p-0002", "他说。"),
                ],
            )

    utterances_by_paragraph = {"p-0002": [_utterance("p-0002-u-001", "p-0002", "“走。”他说。")]}
    segmentation = FakeSegmentationService()
    service = BatchRoleSelectionService(FakeBatchSkill(), segmentation_service=segmentation)

    report = service.select_roles_for_statements_batch(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        paragraphs=[{"paragraph_id": "p-0002", "text": "“走。”他说。"}],
        utterances_by_paragraph=utterances_by_paragraph,
        roles=[_role("narrator", "旁白"), _role("hero", "林清", "voice-hero")],
    )

    assert report.status == "completed"
    assert segmentation.calls == ["p-0002"]
    assert [item["text"] for item in utterances_by_paragraph["p-0002"]] == ["“走。”", "他说。"]
    assert [item["speaker_role_id"] for item in utterances_by_paragraph["p-0002"]] == ["hero", "narrator"]
    assert report.split_count == 1


def test_v0_32_batch_role_selection_keeps_speech_tag_narration_as_narrator_after_split():
    """Covers v0.3.2: quoted speech belongs to speaker, trailing speech tag belongs to narrator."""
    from backend.app.domain.ai_one_click_workflow import BatchRoleSelectionService
    from backend.app.domain.segmentation import SegmentationValidationResult

    class OvereagerPeruoBatchSkill:
        def __init__(self):
            self.calls = []

        def choose_roles_batch(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "items": [
                    {
                        "statement_id": "p-0003-u-001",
                        "action": "select_role",
                        "role_id": "peruo",
                        "confidence": 0.92,
                        "reason": "quoted speech by Peruo",
                        "evidence": "都怪你多嘴",
                    },
                    {
                        "statement_id": "p-0003-u-002",
                        "action": "select_role",
                        "role_id": "peruo",
                        "confidence": 0.88,
                        "reason": "mentions Peruo",
                        "evidence": "佩罗恼火道",
                    },
                ]
            }

    class SpeechTagSegmentationService:
        def __init__(self):
            self.calls = []

        def segment_paragraph(self, *, paragraph_id, **kwargs):
            self.calls.append(paragraph_id)
            return SegmentationValidationResult(
                ok=True,
                paragraph_id=paragraph_id,
                utterances=[
                    _utterance("p-0003-u-001", "p-0003", "“都怪你多嘴，她认出我们了。”"),
                    _utterance("p-0003-u-002", "p-0003", "佩罗恼火道。"),
                ],
            )

    utterances_by_paragraph = {
        "p-0003": [_utterance("p-0003-u-001", "p-0003", "“都怪你多嘴，她认出我们了。”佩罗恼火道。")]
    }
    role_skill = OvereagerPeruoBatchSkill()
    service = BatchRoleSelectionService(
        role_skill,
        segmentation_service=SpeechTagSegmentationService(),
    )

    report = service.select_roles_for_statements_batch(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        paragraphs=[{"paragraph_id": "p-0003", "text": "“都怪你多嘴，她认出我们了。”佩罗恼火道。"}],
        utterances_by_paragraph=utterances_by_paragraph,
        roles=[_role("narrator", "旁白"), _role("peruo", "佩罗", "voice-peruo")],
    )

    assert report.status == "completed"
    assert [item["text"] for item in utterances_by_paragraph["p-0003"]] == [
        "“都怪你多嘴，她认出我们了。”",
        "佩罗恼火道。",
    ]
    assert [[item["text"] for item in call["statements"]] for call in role_skill.calls] == [
        ["“都怪你多嘴，她认出我们了。”", "佩罗恼火道。"]
    ]
    assert [item["speaker_role_id"] for item in utterances_by_paragraph["p-0003"]] == ["peruo", "narrator"]
    assert report.success_count == 2
    assert report.split_count == 1


def test_v0_30_batch_role_selection_invalid_json_writes_nothing():
    """Covers v0.3.0 JSON failure safety for batch role selection."""
    from backend.app.domain.ai_one_click_workflow import BatchRoleSelectionService

    class BrokenBatchSkill:
        def choose_roles_batch(self, **kwargs):
            return "{not-json"

    utterances_by_paragraph = {"p-0001": [_utterance("p-0001-u-001", "p-0001", "待判断。")]}
    service = BatchRoleSelectionService(BrokenBatchSkill())

    report = service.select_roles_for_statements_batch(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        paragraphs=[{"paragraph_id": "p-0001", "text": "待判断。"}],
        utterances_by_paragraph=utterances_by_paragraph,
        roles=[_role("narrator", "旁白")],
    )

    assert report.status == "failed"
    assert utterances_by_paragraph["p-0001"][0]["speaker_role_id"] is None
    assert report.failed_count == 1
    assert "JSON" in report.errors[0]["message"]


def test_v0_30_auto_role_creation_dedupes_narrator_binds_or_generates_voice():
    """Covers v0.3.0 automatic role creation and voice matching/generation."""
    from backend.app.domain.ai_one_click_workflow import (
        RoleAnalysisCandidate,
        auto_apply_role_candidates,
    )
    from backend.app.domain.roles import RoleCollection
    from backend.app.domain.voices import VoiceResourceCollection

    roles = RoleCollection([_role("narrator", "旁白")])
    voices = VoiceResourceCollection(
        [
            {
                "voice_id": "voice-calm-female",
                "name": "冷静女声",
                "gender": "女",
                "description": "冷静、清亮，适合女性主角对白。",
                "suitable_role_types": ["女性主角", "冷静"],
                "reference_text": "测试语音",
                "reference_audio_path": "female.wav",
            }
        ]
    )
    generated = []

    def generate_voice(candidate):
        generated.append(candidate.name)
        return {
            "voice_id": "voice-generated-peruo",
            "name": "佩罗专属音色",
            "gender": "男",
            "description": "懒散男声",
            "suitable_role_types": ["男", "佣兵"],
            "reference_text": "佩罗的试听语音。",
            "reference_audio_path": "peruo.wav",
            "generated": True,
        }

    result = auto_apply_role_candidates(
        candidates=[
            RoleAnalysisCandidate(name="旁白", profile="叙述者", voice_direction="沉稳旁白"),
            RoleAnalysisCandidate(name="林清", aliases=["大小姐"], gender="女", profile="冷静女性主角"),
            RoleAnalysisCandidate(name="佩罗", gender="男", profile="懒散佣兵", voice_direction="懒散男声"),
        ],
        roles=roles,
        voices=voices,
        generate_voice=generate_voice,
    )

    role_names = [role.name for role in roles.list()]
    assert role_names.count("旁白") == 1
    assert "林清" in role_names
    assert "佩罗" in role_names
    assert roles.get("role-linqing").voice_resource_id == "voice-calm-female"
    assert roles.get("role-linqing").voice_generated_by_ai is False
    assert roles.get("role-peiluo").voice_resource_id == "voice-generated-peruo"
    assert roles.get("role-peiluo").voice_generated_by_ai is True
    assert voices.get("voice-generated-peruo").generated is True
    assert generated == ["佩罗"]
    assert result.added_count == 2
    assert result.matched_existing_count == 1


def test_v0_30_one_click_dubbing_groups_by_voice_and_maps_results_by_statement_id(tmp_path):
    """Covers v0.3.0 grouped batch TTS generation, result mapping, and success skip."""
    from backend.app.domain.audio import generate_chapter_audio_batch

    utterances_by_paragraph = {
        "p-0001": [
            {
                **_utterance("p-0001-u-001", "p-0001", "已生成。", "narrator"),
                "audio_status": "success",
                "audio_path": "old.wav",
            },
            _utterance("p-0001-u-002", "p-0001", "第一句。", "narrator"),
            _utterance("p-0001-u-003", "p-0001", "第二句。", "hero"),
            _utterance("p-0001-u-004", "p-0001", "第三句。", "hero"),
        ]
    }
    calls = []

    def synthesize_batch(request, *, output_dir):
        calls.append(request)
        return [
            {
                "statement_id": statement_id,
                "audio_path": str(output_dir / f"{statement_id}.wav"),
                "audio_duration": 0.75,
                "provider": "fake-batch-tts",
                "model": "fake",
            }
            for statement_id in request["statement_ids"]
        ]

    report = generate_chapter_audio_batch(
        chapter_id="chapter-0001",
        utterances_by_paragraph=utterances_by_paragraph,
        roles=[_role("narrator", "旁白", "voice-a"), _role("hero", "林清", "voice-b")],
        output_dir=tmp_path,
        synthesize_batch=synthesize_batch,
    )

    assert report.status == "completed"
    assert report.skipped_count == 1
    assert report.success_count == 3
    assert len(calls) == 2
    assert [call["voice_resource_id"] for call in calls] == ["voice-a", "voice-b"]
    assert calls[0]["statement_ids"] == ["p-0001-u-002"]
    assert calls[1]["statement_ids"] == ["p-0001-u-003", "p-0001-u-004"]
    assert utterances_by_paragraph["p-0001"][0]["audio_path"] == "old.wav"
    assert utterances_by_paragraph["p-0001"][3]["audio_path"].endswith("p-0001-u-004.wav")
    assert utterances_by_paragraph["p-0001"][3]["audio_provider"] == "fake-batch-tts"


def test_v0_30_export_writes_manifest_and_full_audio_only_when_complete(tmp_path):
    """Covers v0.3.0 per-line export manifest and complete-chapter concatenation gate."""
    from backend.app.domain.audio import export_chapter_audio, write_silent_wav

    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    write_silent_wav(first, duration_seconds=0.6)
    write_silent_wav(second, duration_seconds=0.6)
    utterances_by_paragraph = {
        "p-0001": [
            {
                **_utterance("p-0001-u-001", "p-0001", "第一句。", "narrator"),
                "audio_status": "success",
                "audio_path": str(first),
                "audio_duration": 0.6,
            },
            {
                **_utterance("p-0001-u-002", "p-0001", "第二句。", "hero"),
                "audio_status": "success",
                "audio_path": str(second),
                "audio_duration": 0.6,
            },
        ]
    }

    complete = export_chapter_audio(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        utterances_by_paragraph=utterances_by_paragraph,
        roles=[_role("narrator", "旁白", "voice-a"), _role("hero", "林清", "voice-b")],
        output_dir=tmp_path / "export-complete",
    )

    assert complete.missing_count == 0
    assert complete.full_audio_path is not None
    assert Path(complete.full_audio_path).exists()
    manifest = json.loads(Path(complete.manifest_path).read_text(encoding="utf-8"))
    assert [item["filename"] for item in manifest["items"]] == [
        "c0001_p0001_u0001_旁白.wav",
        "c0001_p0001_u0002_林清.wav",
    ]

    utterances_by_paragraph["p-0001"][1]["audio_status"] = "failed"
    incomplete = export_chapter_audio(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        utterances_by_paragraph=utterances_by_paragraph,
        roles=[_role("narrator", "旁白", "voice-a"), _role("hero", "林清", "voice-b")],
        output_dir=tmp_path / "export-incomplete",
    )

    assert incomplete.missing_count == 1
    assert incomplete.full_audio_path is None
    assert not (tmp_path / "export-incomplete" / "chapter_full.wav").exists()


def test_v0_30_role_delete_blocks_referenced_role_unless_unbound_or_migrated():
    """Covers v0.3.0 role deletion constraints."""
    from backend.app.domain.roles import RoleCollection

    roles = RoleCollection([_role("narrator", "旁白"), _role("hero", "林清", "voice-hero")])
    utterances_by_paragraph = {"p-0001": [_utterance("p-0001-u-001", "p-0001", "台词。", "hero")]}

    blocked = roles.delete_with_policy("hero", utterances_by_paragraph)
    assert blocked.deleted is False
    assert blocked.referenced_count == 1
    assert roles.get("hero").name == "林清"

    unbound = roles.delete_with_policy("hero", utterances_by_paragraph, action="unbind")
    assert unbound.deleted is True
    assert utterances_by_paragraph["p-0001"][0]["speaker_role_id"] is None

    roles.upsert(_role("hero", "林清", "voice-hero"))
    utterances_by_paragraph["p-0001"][0]["speaker_role_id"] = "hero"
    migrated = roles.delete_with_policy(
        "hero",
        utterances_by_paragraph,
        action="migrate",
        target_role_id="narrator",
    )
    assert migrated.deleted is True
    assert utterances_by_paragraph["p-0001"][0]["speaker_role_id"] == "narrator"
