from __future__ import annotations

import base64
import io
import zipfile


def make_epub_bytes(chapters: list[tuple[str, str]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
</container>""",
        )
        manifest_items = []
        spine_items = []
        for index, (title, body) in enumerate(chapters, start=1):
            href = f"chapters/chapter{index}.xhtml"
            manifest_items.append(f'<item id="chapter{index}" href="{href}" media-type="application/xhtml+xml"/>')
            spine_items.append(f'<itemref idref="chapter{index}"/>')
            archive.writestr(
                f"OEBPS/{href}",
                f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>{title}</title></head>
  <body><h1>{title}</h1><p>{body}</p></body>
</html>""",
            )
        archive.writestr(
            "OEBPS/content.opf",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest>{''.join(manifest_items)}</manifest>
  <spine>{''.join(spine_items)}</spine>
</package>""",
        )
    return buffer.getvalue()


def test_v0_22_extracts_epub_spine_text_for_ai_agent():
    """EPUB files are converted into chapter-like text in spine order."""
    from backend.app.domain.novel_files import extract_novel_file_text

    text = extract_novel_file_text(
        filename="mushroom.epub",
        data=make_epub_bytes(
            [
                ("1.变成蘑菇的公爵千金", "第一章正文。"),
                ("2.蘑菇园来了个外乡菇", "第二章正文。"),
            ]
        ),
    )

    assert text.index("1.变成蘑菇的公爵千金") < text.index("2.蘑菇园来了个外乡菇")
    assert "第一章正文。" in text
    assert "第二章正文。" in text


def test_v0_22_epub_unseen_heading_style_calls_skill_and_saves_parser(tmp_path):
    """Unseen EPUB text still goes through the skill, writes a script, and validates output."""
    from backend.app.domain.ai_chapter_agent import (
        AiChapterSplitAgent,
        ChapterSplitSkill,
        ChapterSplitValidation,
    )
    from backend.app.domain.novel_files import extract_novel_file_text

    text = extract_novel_file_text(
        filename="node-style.epub",
        data=make_epub_bytes(
            [
                ("MUSHROOM NODE :: Prologue", "Node prologue body."),
                ("MUSHROOM NODE :: Bloom", "Node bloom body."),
            ]
        ),
    )

    class NodeSkill(ChapterSplitSkill):
        def __init__(self):
            self.review_calls = 0

        def create_parser_script(self, *, novel_text, failed_attempts, existing_script_names):
            assert "MUSHROOM NODE :: Prologue" in novel_text
            return """import json
import re
import sys

# 划分 MUSHROOM NODE :: Title 格式
text = sys.stdin.read()
matches = list(re.finditer(r"^(MUSHROOM NODE :: .+)$", text, re.MULTILINE))
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
            return ChapterSplitValidation(True, [])

    skill = NodeSkill()
    result = AiChapterSplitAgent(scripts_dir=tmp_path, skill=skill).split(text)

    assert result.status == "script_created"
    assert skill.review_calls == 1
    assert result.script_path and result.script_path.exists()
    assert "划分 MUSHROOM NODE :: Title 格式" in result.script_path.read_text(encoding="utf-8")
    assert [chapter.title for chapter in result.chapters] == [
        "MUSHROOM NODE :: Prologue",
        "MUSHROOM NODE :: Bloom",
    ]


def test_v0_22_curated_parser_prefers_epub_numeric_titles_over_body_headings(tmp_path):
    """EPUB h1 numeric titles beat incidental body lines such as 第一章..."""
    import shutil
    from pathlib import Path

    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill
    from backend.app.domain.novel_files import extract_novel_file_text

    scripts_dir = tmp_path / "chapter_parsers"
    scripts_dir.mkdir()
    parser_source = Path(__file__).resolve().parents[1] / "scripts/chapter_parsers/chinese_numeric_headings.py"
    shutil.copy(parser_source, scripts_dir / "chinese_numeric_headings.py")
    text = extract_novel_file_text(
        filename="mushroom.epub",
        data=make_epub_bytes(
            [
                ("1.变成蘑菇的公爵千金", "第一章，人体七大魔力节点模型？正文。"),
                ("2.蘑菇园来了个外乡菇", "第二章并不是这里的标题。"),
                ("3.公爵的怒火", "第三章也只是正文句子。"),
            ]
        ),
    )

    class ExplodingSkill(ChapterSplitSkill):
        def create_parser_script(self, *args, **kwargs):  # pragma: no cover - must not run.
            raise AssertionError("curated parser should prefer numeric EPUB headings")

    result = AiChapterSplitAgent(scripts_dir=scripts_dir, skill=ExplodingSkill()).split(text)

    assert result.status == "script_reused"
    assert [chapter.title for chapter in result.chapters] == [
        "1.变成蘑菇的公爵千金",
        "2.蘑菇园来了个外乡菇",
        "3.公爵的怒火",
    ]


def test_fastapi_v0_22_ai_chapter_split_file_epub_updates_workbench(tmp_path, monkeypatch):
    """The API accepts base64 EPUB files and passes extracted text into the chapter agent."""
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app
    from backend.app.domain.novel import Chapter

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def split(self, text):
            assert "1.变成蘑菇的公爵千金" in text
            assert "第一章正文。" in text

            class Result:
                def __init__(self):
                    self.chapters = [
                        Chapter("chapter-0001", "1.变成蘑菇的公爵千金", "第一章正文。"),
                        Chapter("chapter-0002", "2.蘑菇园来了个外乡菇", "第二章正文。"),
                    ]
                    self.status = "script_reused"
                    self.script_path = tmp_path / "chapter_parsers/chinese_numeric_headings.py"
                    self.trace = ["epub extracted", "script reused"]
                    self.validation = type("Validation", (), {"ok": True, "errors": []})()

            return Result()

    monkeypatch.setattr(app_module, "CHAPTER_PARSER_SCRIPT_DIR", tmp_path / "chapter_parsers")
    monkeypatch.setattr(app_module, "AiChapterSplitAgent", FakeAgent)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")

    client = TestClient(create_app())
    response = client.post(
        "/api/novels/ai-chapter-split-file",
        json={
            "filename": "mushroom.epub",
            "content_base64": base64.b64encode(
                make_epub_bytes(
                    [
                        ("1.变成蘑菇的公爵千金", "第一章正文。"),
                        ("2.蘑菇园来了个外乡菇", "第二章正文。"),
                    ]
                )
            ).decode("ascii"),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"]["kind"] == "epub"
    assert [chapter["title"] for chapter in data["chapters"]] == [
        "1.变成蘑菇的公爵千金",
        "2.蘑菇园来了个外乡菇",
    ]
    assert client.get("/api/chapters").json()["chapters"][0]["title"] == "1.变成蘑菇的公爵千金"
