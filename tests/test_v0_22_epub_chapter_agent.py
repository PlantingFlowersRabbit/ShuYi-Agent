from __future__ import annotations

import io
import json
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
            manifest_items.append(
                f'<item id="chapter{index}" href="{href}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="chapter{index}"/>')
            archive.writestr(
                f"OEBPS/{href}",
                f"""<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head><body><h1>{title}</h1><p>{body}</p></body></html>""",
            )
        archive.writestr(
            "OEBPS/content.opf",
            f"""<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<manifest>{"".join(manifest_items)}</manifest><spine>{"".join(spine_items)}</spine></package>""",
        )
    return buffer.getvalue()


def test_extracts_epub_spine_text_for_novel_parser_agent():
    """EPUB 应按书脊顺序转换为可解析文本。"""
    from backend.app.domain.novel_files import extract_novel_file_text

    text = extract_novel_file_text(
        filename="mushroom.epub",
        data=make_epub_bytes(
            [("1.测试章节甲", "第一章正文。"), ("2.测试章节乙", "第二章正文。")]
        ),
    )

    assert text.index("1.测试章节甲") < text.index("2.测试章节乙")
    assert "第一章正文。" in text


def test_unseen_epub_heading_style_saves_json_rule(tmp_path):
    """未知 EPUB 标题格式应生成并保存 JSON 规则。"""
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
        def create_parser_rule(self, **_kwargs):
            return json.dumps(
                {
                    "heading_pattern": r"^(MUSHROOM NODE :: .+)$",
                    "description": "MUSHROOM NODE 标题",
                }
            )

        def review_chapter_split(self, **_kwargs):
            return ChapterSplitValidation(True, [])

    result = AiChapterSplitAgent(rules_dir=tmp_path, skill=NodeSkill()).split(text)

    assert result.status == "rule_created"
    assert result.rule_path and result.rule_path.suffix == ".json"
    assert [chapter.title for chapter in result.chapters] == [
        "MUSHROOM NODE :: Prologue",
        "MUSHROOM NODE :: Bloom",
    ]


def test_bundled_numeric_rule_beats_incidental_body_headings(tmp_path):
    """规则竞争时应选择覆盖正文更多的 EPUB 数字目录。"""
    from backend.app.api.app import BUNDLED_CHAPTER_RULE_DIR
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent, ChapterSplitSkill
    from backend.app.domain.novel_files import extract_novel_file_text

    text = extract_novel_file_text(
        filename="mushroom.epub",
        data=make_epub_bytes(
            [
                ("1.测试章节甲", "第一章，人体七大魔力节点模型？正文。"),
                ("2.测试章节乙", "第二章并不是这里的标题。"),
                ("3.测试章节丙", "第三章也只是正文句子。"),
            ]
        ),
    )

    result = AiChapterSplitAgent(
        rules_dir=tmp_path,
        bundled_rules_dir=BUNDLED_CHAPTER_RULE_DIR,
        skill=ChapterSplitSkill(),
    ).split(text)

    assert result.rule_path and result.rule_path.name == "numeric_heading.json"
    assert [chapter.title for chapter in result.chapters] == [
        "1.测试章节甲",
        "2.测试章节乙",
        "3.测试章节丙",
    ]


def test_api_epub_split_updates_chapter_workbench(tmp_path, monkeypatch):
    """EPUB 上传结果应进入文本模型并更新章节工作台。"""
    from fastapi.testclient import TestClient

    from backend.app.api import app as app_module
    from backend.app.api.app import create_app
    from backend.app.domain.novel import Chapter

    class FakeAgent:
        def __init__(self, **_kwargs):
            pass

        def split(self, text):
            assert "1.测试章节甲" in text
            return type(
                "Result",
                (),
                {
                    "chapters": [
                        Chapter("chapter-0001", "1.测试章节甲", "第一章正文。"),
                        Chapter("chapter-0002", "2.测试章节乙", "第二章正文。"),
                    ],
                    "status": "rule_reused",
                    "rule_path": tmp_path / "numeric_heading.json",
                    "trace": ["已复用 numeric_heading.json"],
                    "validation": type("Validation", (), {"ok": True, "errors": []})(),
                },
            )()

    monkeypatch.setattr(app_module, "CHAPTER_RULE_DIR", tmp_path / "chapter_rules")
    monkeypatch.setattr(app_module, "AiChapterSplitAgent", FakeAgent)
    monkeypatch.setenv("SHUYI_TEXT_MODEL_API_KEY", "test-deepseek-key")

    client = TestClient(create_app(), headers={"Authorization": "Bearer test-v0-4-token"})
    response = client.post(
        "/api/v1/books/agent-chapter-split-file",
        files={
            "file": (
                "mushroom.epub",
                make_epub_bytes(
                    [
                        ("1.测试章节甲", "第一章正文。"),
                        ("2.测试章节乙", "第二章正文。"),
                    ]
                ),
                "application/epub+zip",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["source"]["kind"] == "epub"
    assert client.get("/api/v1/chapters").json()["chapters"][0]["title"] == "1.测试章节甲"
