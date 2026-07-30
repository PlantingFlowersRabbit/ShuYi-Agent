from __future__ import annotations

import shutil
from pathlib import Path

import pytest

VOLUME_STYLE_TEXT = """第一卷 KEYWORDS
卷首说明。
第四节课发生了些许事件。

第一卷 插图

第一卷 日本的社会结构
社会结构正文。

第一卷 欢迎来到梦幻般的校园生活
校园生活正文。
""".replace("\n", "\r\n")

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


def test_v0_20_agent_reuses_existing_parser_script(tmp_path):
    """Existing scripts are preferred before asking DeepSeek to create a new parser."""
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill

    scripts_dir = tmp_path / "chapter_parsers"
    scripts_dir.mkdir()
    (scripts_dir / "book_style.py").write_text(
        """#!/usr/bin/env python3
import json
import re
import sys

# 划分 Book N: Title 格式
text = sys.stdin.read()
matches = list(re.finditer(r"^(Book \\d+: .+)$", text, re.MULTILINE))
chapters = []
for index, match in enumerate(matches, start=1):
    next_start = matches[index].start() if index < len(matches) else len(text)
    chapters.append({
        "chapter_id": f"chapter-{index:04d}",
        "title": match.group(1),
        "body": text[match.end():next_start].strip(),
    })
print(json.dumps({"chapters": chapters}, ensure_ascii=False))
""",
        encoding="utf-8",
    )

    class ExplodingSkill(ChapterSplitSkill):
        def create_parser_script(self, *args, **kwargs):  # pragma: no cover - must not run.
            raise AssertionError("agent should reuse the existing script")

    result = AiChapterSplitAgent(scripts_dir=scripts_dir, skill=ExplodingSkill()).split(BOOK_STYLE_TEXT)

    assert result.status == "script_reused"
    assert result.script_path and result.script_path.name == "book_style.py"
    assert [chapter.title for chapter in result.chapters] == ["Book 1: Arrival", "Book 2: Departure"]
    assert result.validation.ok is True


def test_v0_20_default_parser_handles_repeated_volume_title_headings_first(tmp_path):
    """The curated parser covers 1973-style 第X卷 title headings before bad generated scripts."""
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill

    scripts_dir = tmp_path / "chapter_parsers"
    scripts_dir.mkdir()
    parser_source = Path(__file__).resolve().parents[1] / "scripts/chapter_parsers/chinese_numeric_headings.py"
    shutil.copy(parser_source, scripts_dir / "chinese_numeric_headings.py")
    (scripts_dir / "agent_generated_bad.py").write_text(
        """import json
print(json.dumps({"chapters": []}, ensure_ascii=False))
""",
        encoding="utf-8",
    )

    class ExplodingSkill(ChapterSplitSkill):
        def create_parser_script(self, *args, **kwargs):  # pragma: no cover - must not run.
            raise AssertionError("curated parser should handle volume headings")

    result = AiChapterSplitAgent(scripts_dir=scripts_dir, skill=ExplodingSkill()).split(VOLUME_STYLE_TEXT)

    assert result.status == "script_reused"
    assert result.script_path and result.script_path.name == "chinese_numeric_headings.py"
    assert result.trace == ["chinese_numeric_headings.py reused"]
    assert [chapter.title for chapter in result.chapters] == [
        "第一卷 KEYWORDS",
        "第一卷 日本的社会结构",
        "第一卷 欢迎来到梦幻般的校园生活",
    ]


def test_v0_20_agent_reflects_and_saves_new_script_when_existing_script_fails(tmp_path):
    """Bad existing scripts are rejected, then the skill creates a reusable parser."""
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill

    scripts_dir = tmp_path / "chapter_parsers"
    scripts_dir.mkdir()
    (scripts_dir / "bad_parser.py").write_text(
        """#!/usr/bin/env python3
import json
import sys

# 划分错误示例：总是返回整本正文
text = sys.stdin.read()
print(json.dumps({"chapters": [{"chapter_id": "chapter-0001", "title": "未分章正文", "body": text}]}))
""",
        encoding="utf-8",
    )

    class FakeSkill(ChapterSplitSkill):
        def __init__(self):
            self.calls = 0

        def create_parser_script(self, *, novel_text, failed_attempts, existing_script_names):
            self.calls += 1
            assert "bad_parser.py" in existing_script_names
            assert failed_attempts
            return """#!/usr/bin/env python3
import json
import re
import sys

# 划分 PART-XX Title 格式
text = sys.stdin.read()
matches = list(re.finditer(r"^(PART-\\d+ .+)$", text, re.MULTILINE))
chapters = []
for index, match in enumerate(matches, start=1):
    next_start = matches[index].start() if index < len(matches) else len(text)
    chapters.append({
        "chapter_id": f"chapter-{index:04d}",
        "title": match.group(1),
        "body": text[match.end():next_start].strip(),
    })
print(json.dumps({"chapters": chapters}, ensure_ascii=False))
"""

    skill = FakeSkill()
    result = AiChapterSplitAgent(scripts_dir=scripts_dir, skill=skill).split(PART_STYLE_TEXT)

    assert result.status == "script_created"
    assert skill.calls == 1
    assert result.script_path and result.script_path.exists()
    assert "划分 PART-XX Title 格式" in result.script_path.read_text(encoding="utf-8")
    assert [chapter.title for chapter in result.chapters] == ["PART-01 Mist", "PART-02 Fire"]
    assert any("bad_parser.py" in item for item in result.trace)


def test_v0_20_generated_parser_runs_ai_review_before_acceptance(tmp_path):
    """New parser scripts require the skill's AI review in addition to rule checks."""
    from backend.app.domain.ai_chapter_agent import (
        AiChapterSplitAgent,
        ChapterSplitSkill,
        ChapterSplitValidation,
    )

    scripts_dir = tmp_path / "chapter_parsers"
    scripts_dir.mkdir()

    class ReviewingSkill(ChapterSplitSkill):
        def __init__(self):
            self.review_calls = 0

        def create_parser_script(self, *, novel_text, failed_attempts, existing_script_names):
            return """#!/usr/bin/env python3
import json
import re
import sys

# 划分 PART-XX Title 格式
text = sys.stdin.read()
matches = list(re.finditer(r"^(PART-\\d+ .+)$", text, re.MULTILINE))
chapters = []
for index, match in enumerate(matches, start=1):
    next_start = matches[index].start() if index < len(matches) else len(text)
    chapters.append({
        "chapter_id": f"chapter-{index:04d}",
        "title": match.group(1),
        "body": text[match.end():next_start].strip(),
    })
print(json.dumps({"chapters": chapters}, ensure_ascii=False))
"""

        def review_chapter_split(self, *, novel_text, chapters, script_content):
            self.review_calls += 1
            assert "PART-01 Mist" in novel_text
            assert [chapter.title for chapter in chapters] == ["PART-01 Mist", "PART-02 Fire"]
            assert "划分 PART-XX Title 格式" in script_content
            return ChapterSplitValidation(True, [])

    skill = ReviewingSkill()
    result = AiChapterSplitAgent(scripts_dir=scripts_dir, skill=skill).split(PART_STYLE_TEXT)

    assert result.status == "script_created"
    assert skill.review_calls == 1
    assert any("AI validation accepted" in item for item in result.trace)


def test_fastapi_v0_20_ai_chapter_split_endpoint_and_config(tmp_path, monkeypatch):
    """The API exposes DeepSeek chapter-agent config and returns agent-split chapters."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app
    from backend.app.domain.novel import Chapter

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def split(self, text):
            assert text == BOOK_STYLE_TEXT

            class Result:
                def __init__(self):
                    self.chapters = [
                        Chapter("chapter-0001", "Book 1: Arrival", "The door opened."),
                        Chapter("chapter-0002", "Book 2: Departure", "The road vanished."),
                    ]
                    self.status = "script_reused"
                    self.script_path = tmp_path / "chapter_parsers/book_style.py"
                    self.trace = ["script reused"]
                    self.validation = type("Validation", (), {"ok": True, "errors": []})()

            return Result()

    monkeypatch.setattr(app_module, "CHAPTER_PARSER_SCRIPT_DIR", tmp_path / "chapter_parsers")
    monkeypatch.setattr(app_module, "AiChapterSplitAgent", FakeAgent)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")

    client = TestClient(create_app())
    config = client.get("/api/model-config").json()["config"]
    assert config["chapter_agent"]["base_url"] == "https://api.deepseek.com"
    assert config["chapter_agent"]["model"] == "deepseek-v4-flash"
    assert config["chapter_agent"]["api_key"] == ""

    updated = client.patch(
        "/api/model-config",
        json={"chapter_agent": {"base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash"}},
    )
    assert updated.status_code == 200

    response = client.post("/api/novels/ai-chapter-split", json={"text": BOOK_STYLE_TEXT})
    assert response.status_code == 200
    data = response.json()
    assert [chapter["title"] for chapter in data["chapters"]] == ["Book 1: Arrival", "Book 2: Departure"]
    assert data["agent"]["status"] == "script_reused"
    assert client.get("/api/chapters").json()["chapters"][0]["title"] == "Book 1: Arrival"
