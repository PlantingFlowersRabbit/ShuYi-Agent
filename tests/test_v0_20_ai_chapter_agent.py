from __future__ import annotations

import json

import pytest

BOOK_STYLE_TEXT = """Book 1: Arrival
The door opened.

Book 2: Departure
The road vanished.
"""

PART_STYLE_TEXT = """PART-01 Mist
First body.

PART-02 Fire
Second body.
"""

VOLUME_STYLE_TEXT = """第一卷 KEYWORDS
卷首说明。
第四节课发生了些许事件。

第一卷 插图

第一卷 日本的社会结构
社会结构正文。

第一卷 欢迎来到梦幻般的校园生活
校园生活正文。
"""


def _write_rule(directory, filename: str, pattern: str, description: str) -> None:
    (directory / filename).write_text(
        json.dumps(
            {"heading_pattern": pattern, "description": description},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_agent_reuses_existing_chapter_rule(tmp_path):
    """已有 JSON 章节规则应优先于模型调用。"""
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill

    rules_dir = tmp_path / "chapter_rules"
    rules_dir.mkdir()
    _write_rule(rules_dir, "book_style.json", r"^(Book \d+: .+)$", "Book 章节")

    class ExplodingSkill(ChapterSplitSkill):
        def create_parser_rule(self, *args, **kwargs):
            raise AssertionError("不应调用模型创建规则")

    result = AiChapterSplitAgent(rules_dir=rules_dir, skill=ExplodingSkill()).split(BOOK_STYLE_TEXT)

    assert result.status == "rule_reused"
    assert result.rule_path and result.rule_path.name == "book_style.json"
    assert [chapter.title for chapter in result.chapters] == [
        "Book 1: Arrival",
        "Book 2: Departure",
    ]


def test_bundled_rule_handles_repeated_volume_titles(tmp_path):
    """随版本发布的规则应识别中文卷标题并忽略空正文候选。"""
    from backend.app.api.app import BUNDLED_CHAPTER_RULE_DIR
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill

    result = AiChapterSplitAgent(
        rules_dir=tmp_path,
        bundled_rules_dir=BUNDLED_CHAPTER_RULE_DIR,
        skill=ChapterSplitSkill(),
    ).split(VOLUME_STYLE_TEXT)

    assert result.status == "rule_reused"
    assert result.rule_path and result.rule_path.name == "chinese_volume.json"
    assert [chapter.title for chapter in result.chapters] == [
        "第一卷 KEYWORDS",
        "第一卷 日本的社会结构",
        "第一卷 欢迎来到梦幻般的校园生活",
    ]


def test_agent_reflects_and_saves_new_json_rule(tmp_path):
    """已有规则失败后，Agent 只能保存结构化 JSON 规则。"""
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill

    _write_rule(tmp_path, "bad_rule.json", r"^(NEVER MATCHES)$", "错误规则")

    class FakeSkill(ChapterSplitSkill):
        def __init__(self):
            self.calls = 0

        def create_parser_rule(self, *, novel_text, failed_attempts, existing_rule_names):
            self.calls += 1
            assert "bad_rule.json" in existing_rule_names
            assert failed_attempts
            return json.dumps(
                {
                    "heading_pattern": r"^(PART-\d+ .+)$",
                    "description": "划分 PART-XX 标题",
                }
            )

        def review_chapter_split(self, **_kwargs):
            from backend.app.domain.ai_chapter_agent import ChapterSplitValidation

            return ChapterSplitValidation(True, [])

    skill = FakeSkill()
    result = AiChapterSplitAgent(rules_dir=tmp_path, skill=skill).split(PART_STYLE_TEXT)

    assert result.status == "rule_created"
    assert skill.calls == 1
    assert result.rule_path and result.rule_path.suffix == ".json"
    assert not list(tmp_path.glob("*.py"))


def test_generated_rule_requires_agent_review(tmp_path):
    """新章节规则在保存前必须经过 Agent 复核。"""
    from backend.app.domain.ai_chapter_agent import (
        AiChapterSplitAgent,
        ChapterSplitSkill,
        ChapterSplitValidation,
    )

    class ReviewingSkill(ChapterSplitSkill):
        def __init__(self):
            self.review_calls = 0

        def create_parser_rule(self, **_kwargs):
            return json.dumps(
                {
                    "heading_pattern": r"^(PART-\d+ .+)$",
                    "description": "划分 PART-XX 标题",
                }
            )

        def review_chapter_split(self, *, novel_text, chapters, rule_content):
            self.review_calls += 1
            assert "PART-01 Mist" in novel_text
            assert [chapter.title for chapter in chapters] == ["PART-01 Mist", "PART-02 Fire"]
            assert "heading_pattern" in rule_content
            return ChapterSplitValidation(True, [])

    skill = ReviewingSkill()
    result = AiChapterSplitAgent(rules_dir=tmp_path, skill=skill).split(PART_STYLE_TEXT)

    assert result.status == "rule_created"
    assert skill.review_calls == 1
    assert "Agent 复核通过" in result.trace


def test_api_chapter_split_uses_rule_directory_and_updates_chapters(tmp_path, monkeypatch):
    """API 应调用文本模型，并用结果更新章节目录。"""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app
    from backend.app.domain.novel import Chapter

    class FakeAgent:
        def __init__(self, **kwargs):
            assert "rules_dir" in kwargs

        def split(self, text):
            assert text == BOOK_STYLE_TEXT
            return type(
                "Result",
                (),
                {
                    "chapters": [
                        Chapter("chapter-0001", "Book 1: Arrival", "The door opened."),
                        Chapter("chapter-0002", "Book 2: Departure", "The road vanished."),
                    ],
                    "status": "rule_reused",
                    "rule_path": tmp_path / "book_style.json",
                    "trace": ["已复用 book_style.json"],
                    "validation": type("Validation", (), {"ok": True, "errors": []})(),
                },
            )()

    monkeypatch.setattr(app_module, "CHAPTER_RULE_DIR", tmp_path / "chapter_rules")
    monkeypatch.setattr(app_module, "AiChapterSplitAgent", FakeAgent)
    monkeypatch.setenv("SHUYI_TEXT_MODEL_API_KEY", "test-deepseek-key")

    client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
    response = client.post(
        "/api/v1/books/agent-chapter-split",
        json={"text": BOOK_STYLE_TEXT},
    )

    assert response.status_code == 200
    assert [chapter["title"] for chapter in response.json()["chapters"]] == [
        "Book 1: Arrival",
        "Book 2: Departure",
    ]
    assert client.get("/api/v1/chapters").json()["chapters"][0]["title"] == "Book 1: Arrival"
