import re
from dataclasses import dataclass

CHAPTER_HEADING_RE = re.compile(
    r"^[ \t]*((?:第[一二三四五六七八九十百千万零〇两\d]+[章节回][^\n\r]*)|(?:\d+[.．、][^\n\r]*))$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Chapter:
    chapter_id: str
    title: str
    body: str


@dataclass
class ParagraphModule:
    paragraph_id: str
    text: str
    collapsed: bool = False
    deleted: bool = False
    confirmed: bool = False


def parse_novel_text(text: str) -> list[Chapter]:
    matches = list(CHAPTER_HEADING_RE.finditer(text))
    if not matches:
        stripped = text.strip()
        return (
            [Chapter(chapter_id="chapter-0001", title="未分章正文", body=stripped)]
            if stripped
            else []
        )

    chapters: list[Chapter] = []
    for index, match in enumerate(matches, start=1):
        next_start = matches[index].start() if index < len(matches) else len(text)
        body = text[match.end() : next_start].strip()
        body = re.sub(r"^-{3,}\s*", "", body).strip()
        chapters.append(
            Chapter(
                chapter_id=f"chapter-{index:04d}",
                title=match.group(1).strip(),
                body=body,
            )
        )
    return chapters


def split_paragraphs(body: str) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue

        starts_indented_paragraph = bool(re.match(r"^[\u3000]{1,}", line))
        if starts_indented_paragraph and current:
            paragraphs.append("\n".join(current).strip())
            current = []
        current.append(line.strip())

    if current:
        paragraphs.append("\n".join(current).strip())
    return [paragraph for paragraph in paragraphs if paragraph]


class ChapterWorkbench:
    def __init__(self, chapter: Chapter, paragraphs: list[ParagraphModule]):
        self.chapter = chapter
        self._paragraphs = paragraphs
        self._confirmed = False

    @classmethod
    def from_chapter(cls, chapter: Chapter) -> "ChapterWorkbench":
        modules = [
            ParagraphModule(paragraph_id=f"p-{index:04d}", text=text)
            for index, text in enumerate(split_paragraphs(chapter.body), start=1)
        ]
        return cls(chapter, modules)

    @property
    def visible_paragraphs(self) -> list[ParagraphModule]:
        return [paragraph for paragraph in self._paragraphs if not paragraph.deleted]

    @property
    def can_segment(self) -> bool:
        return self._confirmed and bool(self.visible_paragraphs)

    def get_paragraph(self, paragraph_id: str) -> ParagraphModule:
        for paragraph in self._paragraphs:
            if paragraph.paragraph_id == paragraph_id:
                return paragraph
        raise KeyError(f"段落不存在：{paragraph_id}")

    def edit_paragraph(self, paragraph_id: str, text: str) -> None:
        paragraph = self.get_paragraph(paragraph_id)
        paragraph.text = text
        self._confirmed = False
        for item in self._paragraphs:
            item.confirmed = False

    def delete_paragraph(self, paragraph_id: str) -> None:
        paragraph = self.get_paragraph(paragraph_id)
        paragraph.deleted = True
        self._confirmed = False
        paragraph.confirmed = False

    def toggle_paragraph(self, paragraph_id: str) -> None:
        paragraph = self.get_paragraph(paragraph_id)
        paragraph.collapsed = not paragraph.collapsed

    def confirm_paragraphs(self) -> None:
        if not self.visible_paragraphs:
            raise ValueError("不能确认空章节")
        for paragraph in self.visible_paragraphs:
            paragraph.confirmed = True
        self._confirmed = True
