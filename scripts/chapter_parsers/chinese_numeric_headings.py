import json
import re
import sys

# 划分中文“第X章/节/回”和数字编号“1.标题/1、标题”格式
HEADING_RE = re.compile(
    r"^[ \t]*((?:第[一二三四五六七八九十百千万零〇两\d]+[章节回][^\n\r]*)|(?:\d+[.．、][^\n\r]*))$",
    re.MULTILINE,
)


def main() -> None:
    text = sys.stdin.read()
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        stripped = text.strip()
        chapters = [{"chapter_id": "chapter-0001", "title": "未分章正文", "body": stripped}] if stripped else []
    else:
        chapters = []
        for index, match in enumerate(matches, start=1):
            next_start = matches[index].start() if index < len(matches) else len(text)
            body = text[match.end() : next_start].strip()
            body = re.sub(r"^-{3,}\s*", "", body).strip()
            chapters.append(
                {
                    "chapter_id": f"chapter-{index:04d}",
                    "title": match.group(1).strip(),
                    "body": body,
                }
            )
    print(json.dumps({"chapters": chapters}, ensure_ascii=False))


if __name__ == "__main__":
    main()
