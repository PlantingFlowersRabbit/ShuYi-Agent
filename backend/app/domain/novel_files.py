from __future__ import annotations

import html
import posixpath
import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from typing import ClassVar
from xml.etree import ElementTree


@dataclass(frozen=True)
class NovelFileExtraction:
    kind: str
    text: str


class NovelFileError(ValueError):
    pass


def extract_novel_file_text(*, filename: str, data: bytes) -> str:
    return extract_novel_file(filename=filename, data=data).text


def extract_novel_file(*, filename: str, data: bytes) -> NovelFileExtraction:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".epub":
        return NovelFileExtraction("epub", _extract_epub_text(data))
    if suffix == ".txt" or not suffix:
        return NovelFileExtraction("txt", decode_novel_text_bytes(data))
    raise NovelFileError(f"unsupported novel file type: {suffix}")


def decode_novel_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "gbk", "big5"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_epub_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            opf_path = _epub_opf_path(archive)
            chapter_paths = _epub_spine_paths(archive, opf_path)
            if not chapter_paths:
                chapter_paths = _fallback_epub_html_paths(archive)
            sections = [_extract_xhtml_text(archive.read(path)) for path in chapter_paths]
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise NovelFileError(f"invalid epub file: {exc}") from exc
    text = "\n\n".join(section for section in sections if section.strip()).strip()
    if not text:
        raise NovelFileError("epub contains no readable chapter text")
    return text


def _epub_opf_path(archive: zipfile.ZipFile) -> str:
    container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
    for item in container.iter():
        if _local_name(item.tag) == "rootfile":
            path = item.attrib.get("full-path")
            if path:
                return path
    raise NovelFileError("epub container has no rootfile")


def _epub_spine_paths(archive: zipfile.ZipFile, opf_path: str) -> list[str]:
    opf = ElementTree.fromstring(archive.read(opf_path))
    manifest: dict[str, str] = {}
    for item in opf.iter():
        if _local_name(item.tag) == "item":
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            if item_id and href:
                manifest[item_id] = href
    opf_dir = posixpath.dirname(opf_path)
    paths: list[str] = []
    for item in opf.iter():
        if _local_name(item.tag) == "itemref":
            href = manifest.get(item.attrib.get("idref", ""))
            if href:
                paths.append(posixpath.normpath(posixpath.join(opf_dir, href)))
    names = set(archive.namelist())
    return [path for path in paths if path in names and path.lower().endswith((".xhtml", ".html", ".htm"))]


def _fallback_epub_html_paths(archive: zipfile.ZipFile) -> list[str]:
    ignored = ("nav.xhtml", "toc.xhtml", "container.xml")
    return [
        name
        for name in archive.namelist()
        if name.lower().endswith((".xhtml", ".html", ".htm"))
        and not name.lower().endswith(ignored)
    ]


def _extract_xhtml_text(data: bytes) -> str:
    decoded = data.decode("utf-8", errors="replace")
    parser = _XhtmlTextParser()
    parser.feed(decoded)
    return parser.text()


class _XhtmlTextParser(HTMLParser):
    block_tags: ClassVar[set[str]] = {"title", "h1", "h2", "h3", "p", "div", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._current: list[str] = []
        self._lines: list[str] = []
        self._capture_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in self.block_tags:
            self._flush()
            self._capture_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in self.block_tags and self._capture_depth:
            self._flush()
            self._capture_depth -= 1

    def handle_data(self, data: str):
        if self._capture_depth:
            self._current.append(data)

    def text(self) -> str:
        self._flush()
        cleaned: list[str] = []
        previous = ""
        for line in self._lines:
            if line and line != previous:
                cleaned.append(line)
            previous = line
        return "\n".join(cleaned)

    def _flush(self) -> None:
        line = html.unescape("".join(self._current))
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            self._lines.append(line)
        self._current = []


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
