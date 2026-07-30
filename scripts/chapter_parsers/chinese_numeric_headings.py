import json
import re
import sys

# 划分中文“第X章/节/回”、轻小说“第X卷 标题/第X篇 标题”和数字编号“1.标题/1、标题”格式
HEADING_PATTERNS = [
    re.compile(r"^[ \t]*((?:第[一二三四五六七八九十百千万零〇两\d]+[章节回][^\n\r]{0,80}))\r?$", re.MULTILINE),
    re.compile(
        r"^[ \t]*((?:第[一二三四五六七八九十百千万零〇两\d]+[卷部篇][ \t　]+[^\n\r]{1,80}))\r?$",
        re.MULTILINE,
    ),
    re.compile(r"^[ \t]*(\d{1,4}[.．、](?!\d|[0-9]*[%％])[^\n\r]{0,60})\r?$", re.MULTILINE),
]


def find_headings(text: str) -> list[re.Match[str]]:
    candidates: list[list[re.Match[str]]] = []
    for pattern in HEADING_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            candidates.append(matches)
    if not candidates:
        return []
    return max(candidates, key=lambda matches: heading_score(text, matches))


def heading_score(text: str, matches: list[re.Match[str]]) -> tuple[int, int, int]:
    non_empty_bodies = 0
    for index, match in enumerate(matches, start=1):
        next_start = matches[index].start() if index < len(matches) else len(text)
        if text[match.end() : next_start].strip():
            non_empty_bodies += 1
    first_index = matches[0].start() if matches else len(text)
    return non_empty_bodies, len(matches), -first_index


def main() -> None:
    text = sys.stdin.read()
    matches = find_headings(text)
    if not matches:
        stripped = text.strip()
        chapters = [{"chapter_id": "chapter-0001", "title": "未分章正文", "body": stripped}] if stripped else []
    else:
        chapters = []
        for index, match in enumerate(matches, start=1):
            next_start = matches[index].start() if index < len(matches) else len(text)
            body = text[match.end() : next_start].strip()
            body = re.sub(r"^-{3,}\s*", "", body).strip()
            if not body:
                continue
            chapter_index = len(chapters) + 1
            chapters.append(
                {
                    "chapter_id": f"chapter-{chapter_index:04d}",
                    "title": match.group(1).strip(),
                    "body": body,
                }
            )
    print(json.dumps({"chapters": chapters}, ensure_ascii=False))


if __name__ == "__main__":
    main()
