from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import regex as safe_regex

from backend.app.domain.llm import MissingProviderCredential
from backend.app.domain.novel import Chapter

ApiKeyLookup = Callable[[str], str | None]


@dataclass(frozen=True)
class ChapterSplitValidation:
    ok: bool
    errors: list[str]


@dataclass(frozen=True)
class ChapterSplitAgentResult:
    chapters: list[Chapter]
    status: str
    rule_path: Path | None
    validation: ChapterSplitValidation
    trace: list[str]


def validate_chapter_split(text: str, chapters: list[Chapter]) -> ChapterSplitValidation:
    errors: list[str] = []
    if not chapters:
        errors.append("未返回任何章节")
        return ChapterSplitValidation(False, errors)

    for index, chapter in enumerate(chapters, start=1):
        expected_id = f"chapter-{index:04d}"
        if chapter.chapter_id != expected_id:
            errors.append(f"章节编号不连续：期望 {expected_id}，实际为 {chapter.chapter_id}")
        if not chapter.title.strip():
            errors.append(f"{chapter.chapter_id} 的章节标题为空")
        if not chapter.body.strip():
            errors.append(f"{chapter.chapter_id} 的章节正文为空")

    if len(chapters) == 1 and _repeated_heading_like_lines(text) >= 2:
        errors.append("检测到重复章节标题格式，但结果仅包含一个章节")

    source_nonspace = re.sub(r"\s+", "", text)
    body_nonspace = re.sub(r"\s+", "", "".join(chapter.body for chapter in chapters))
    if len(source_nonspace) >= 80 and len(body_nonspace) < int(len(source_nonspace) * 0.25):
        errors.append("章节正文覆盖的小说原稿过少")

    return ChapterSplitValidation(not errors, errors)


def _repeated_heading_like_lines(text: str) -> int:
    signatures: dict[str, int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) > 80:
            continue
        if len(line) < 4:
            continue
        normalized = _heading_signature(line)
        if normalized == line and not re.search(
            r"chapter|book|part|第|卷|章|回", line, re.IGNORECASE
        ):
            continue
        signatures[normalized] = signatures.get(normalized, 0) + 1
    return max(signatures.values(), default=0)


def _heading_signature(line: str) -> str:
    western = re.match(r"^(chapter|book|part)[\s\-_:]*\d+", line, re.IGNORECASE)
    if western:
        return f"{western.group(1).lower()}-#"
    chinese = re.match(r"^(第[一二三四五六七八九十百千万零〇两\d]+[章节回卷])", line)
    if chinese:
        unit = re.sub(r"[一二三四五六七八九十百千万零〇两\d]+", "N", chinese.group(1))
        return unit
    numbered = re.match(r"^\d+[.．、]", line)
    if numbered:
        return "#."
    normalized = re.sub(r"\d+", "#", line)
    return re.sub(r"[一二三四五六七八九十百千万零〇两]+", "N", normalized)


def _chapters_from_payload(payload: Any) -> list[Chapter]:
    raw_chapters = payload.get("chapters") if isinstance(payload, dict) else payload
    if not isinstance(raw_chapters, list):
        raise TypeError("解析结果必须是章节列表，或包含 chapters 的对象")

    chapters: list[Chapter] = []
    for index, item in enumerate(raw_chapters, start=1):
        if not isinstance(item, dict):
            raise TypeError("章节条目必须是对象")
        chapters.append(
            Chapter(
                chapter_id=str(item.get("chapter_id") or f"chapter-{index:04d}"),
                title=str(item.get("title") or "").strip(),
                body=str(item.get("body") or "").strip(),
            )
        )
    return chapters


def _strip_json_fence(content: str) -> str:
    cleaned = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else cleaned


def _chapter_rule_from_model_output(content: str) -> tuple[dict[str, str] | None, str | None]:
    cleaned = content.strip()
    try:
        payload = json.loads(_strip_json_fence(cleaned))
    except json.JSONDecodeError as exc:
        return None, f"模型输出不是有效的章节规则 JSON：{exc}"

    if isinstance(payload, dict) and isinstance(payload.get("heading_pattern"), str):
        description = str(payload.get("description") or "划分自动识别的章节标题格式")
        rule = {"heading_pattern": payload["heading_pattern"], "description": description}
        return _validate_chapter_rule(rule)
    return None, "章节规则必须包含字符串类型的 heading_pattern"


def _validate_chapter_rule(rule: dict[str, str]) -> tuple[dict[str, str] | None, str | None]:
    pattern = rule["heading_pattern"]
    if not pattern or len(pattern) > 500:
        return None, "章节标题正则长度必须在 1 到 500 个字符之间"
    if not pattern.startswith("^"):
        return None, "章节标题正则必须从行首开始匹配"
    nested_quantifier = re.search(r"\([^)]*(?:[+*]|\{\d+(?:,\d*)?\})[^)]*\)(?:[+*]|\{)", pattern)
    if nested_quantifier:
        return None, "标题正则不能包含嵌套量词"
    if _has_overlapping_quantified_alternation(pattern):
        return None, "标题正则不能包含带量词的重叠分支"
    if re.search(r"\\[1-9]|\(\?(?:[=!]|<[=!])", pattern):
        return None, "标题正则不能包含反向引用或环视表达式"
    try:
        compiled = safe_regex.compile(pattern, safe_regex.MULTILINE)
    except safe_regex.error as exc:
        return None, f"章节标题正则无效：{exc}"
    if compiled.groups < 1:
        return None, "章节标题正则必须用第一个捕获组包含完整标题"
    return rule, None


def _has_overlapping_quantified_alternation(pattern: str) -> bool:
    for match in re.finditer(r"\(([^()]+\|[^()]+)\)(?:[+*]|\{\d+(?:,\d*)?\})", pattern):
        group = match.group(1)
        group = group.removeprefix("?:")
        alternatives = [item for item in group.split("|") if item]
        for left_index, left in enumerate(alternatives):
            for right in alternatives[left_index + 1 :]:
                if left.startswith(right) or right.startswith(left):
                    return True
    return False


def _chapters_from_chapter_rule(rule: dict[str, str], text: str) -> list[Chapter]:
    compiled = safe_regex.compile(rule["heading_pattern"])
    matches: list[re.Match[str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        candidate = line.rstrip("\r\n")
        if len(candidate) <= 512:
            try:
                match = compiled.match(candidate, timeout=0.02)
            except TimeoutError as exc:
                raise ValueError("章节标题规则匹配超时") from exc
            if match and match.end() == len(candidate):
                matches.append(_OffsetMatch(match, offset))
        offset += len(line)
    chapters: list[Chapter] = []
    for index, match in enumerate(matches, start=1):
        next_start = matches[index].start() if index < len(matches) else len(text)
        body = text[match.end() : next_start].strip()
        if not body:
            continue
        chapter_index = len(chapters) + 1
        chapters.append(
            Chapter(
                chapter_id=f"chapter-{chapter_index:04d}",
                title=match.group(1).strip(),
                body=body,
            )
        )
    return chapters


class _OffsetMatch:
    """把单行安全匹配的位置转换为小说全文偏移。"""

    def __init__(self, match: Any, offset: int):
        self._match = match
        self._offset = offset

    def start(self) -> int:
        return self._offset + self._match.start()

    def end(self) -> int:
        return self._offset + self._match.end()

    def group(self, index: int) -> str:
        return self._match.group(index)


class ChapterSplitSkill:
    def __init__(
        self,
        *,
        provider: dict[str, Any] | None = None,
        api_key_lookup: ApiKeyLookup | None = None,
        system_prompt: str | None = None,
    ):
        self.provider = provider or {
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "api_key_env": "DEEPSEEK_API_KEY",
            "timeout_seconds": 120,
        }
        self.api_key_lookup = api_key_lookup or (lambda name: None)
        self.system_prompt = system_prompt or (
            "你是书弈 Agent 的小说解析 Agent。只返回描述章节标题规则的 JSON。"
        )

    def _chat_model(self):
        provider = getattr(self, "provider", None) or {}
        api_key_lookup = getattr(self, "api_key_lookup", lambda name: None)
        api_key_env = str(provider.get("api_key_env") or "DEEPSEEK_API_KEY")
        api_key = api_key_lookup(api_key_env)
        if not api_key:
            raise MissingProviderCredential(f"缺少 API 密钥环境变量：{api_key_env}")

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=api_key,
            base_url=str(provider.get("base_url") or "https://api.deepseek.com"),
            model=str(provider.get("model") or "deepseek-v4-flash"),
            temperature=0,
            timeout=int(provider.get("timeout_seconds", 120)),
        )

    def create_parser_rule(
        self,
        *,
        novel_text: str,
        failed_attempts: list[str],
        existing_rule_names: list[str],
    ) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = self._chat_model()
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(
                content=self._build_prompt(novel_text, failed_attempts, existing_rule_names)
            ),
        ]
        response = llm.invoke(messages)
        return _strip_json_fence(str(response.content))

    def review_chapter_split(
        self,
        *,
        novel_text: str,
        chapters: list[Chapter],
        rule_content: str,
    ) -> ChapterSplitValidation:
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = self._chat_model()
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=self._build_review_prompt(novel_text, chapters, rule_content)),
        ]
        response = llm.invoke(messages)
        try:
            payload = json.loads(_strip_json_fence(str(response.content)))
        except json.JSONDecodeError as exc:
            return ChapterSplitValidation(False, [f"Agent 校验返回的 JSON 无效：{exc}"])
        if not isinstance(payload, dict):
            return ChapterSplitValidation(False, ["Agent 校验结果必须是对象"])
        raw_errors = payload.get("errors", [])
        errors = [str(item) for item in raw_errors] if isinstance(raw_errors, list) else []
        ok = bool(payload.get("ok")) and not errors
        return ChapterSplitValidation(ok, errors or ([] if ok else ["Agent 校验未接受章节结果"]))

    def _build_prompt(
        self,
        novel_text: str,
        failed_attempts: list[str],
        existing_rule_names: list[str],
    ) -> str:
        sample = novel_text[:12000]
        failed = "\n".join(f"- {item}" for item in failed_attempts[-6:]) or "- 无"
        rules = ", ".join(existing_rule_names) or "无"
        return f"""
请观察上传 txt 小说开头若干章格式，创建一个章节划分规则。

规则要求：
- 只返回严格 JSON：{{"heading_pattern":"^(捕获完整标题的正则)$","description":"划分什么格式"}}。
- heading_pattern 必须以 ^ 开头，并用第一个捕获组捕获完整标题行。
- 规则按 MULTILINE 模式匹配；不要返回 Python、Markdown 或任何可执行内容。

已有规则：{rules}
失败结果（reflection 输入，避免重复错误）：
{failed}

小说样本：
{sample}
""".strip()

    def _build_review_prompt(
        self,
        novel_text: str,
        chapters: list[Chapter],
        rule_content: str,
    ) -> str:
        sample = novel_text[:8000]
        chapter_summary = [
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "body_preview": chapter.body[:240],
            }
            for chapter in chapters[:20]
        ]
        return f"""
请检查章节划分结果是否可信。

检查重点：
- 章节标题格式是否和小说样本一致。
- 是否漏掉明显章节，或把整本小说错误合并成一章。
- body 是否是标题之后、下一章标题之前的正文。
- chapter_id 是否连续。

只返回 JSON：{{"ok": true, "errors": []}} 或 {{"ok": false, "errors": ["原因"]}}。

小说样本：
{sample}

章节规则：
{rule_content[:6000]}

章节摘要：
{json.dumps(chapter_summary, ensure_ascii=False)}
""".strip()


class AiChapterSplitAgent:
    def __init__(
        self,
        *,
        rules_dir: Path,
        bundled_rules_dir: Path | None = None,
        skill: ChapterSplitSkill,
        max_reflections: int = 2,
    ):
        self.rules_dir = rules_dir
        self.bundled_rules_dir = bundled_rules_dir
        self.skill = skill
        self.max_reflections = max_reflections

    def split(self, text: str) -> ChapterSplitAgentResult:
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        trace: list[str] = []
        failed_attempts: list[str] = []

        rule_paths = sorted(
            {
                path
                for directory in (self.bundled_rules_dir, self.rules_dir)
                if directory is not None and directory.is_dir()
                for path in directory.glob("*.json")
            },
            key=lambda path: (path.name, str(path.parent)),
        )
        reusable_candidates: list[
            tuple[tuple[int, int], Path, list[Chapter], ChapterSplitValidation]
        ] = []
        for rule_path in rule_paths:
            chapters, error = self._run_chapter_rule_file(rule_path, text)
            if error:
                failed_attempts.append(f"{rule_path.name}：{error}")
                trace.append(f"{rule_path.name} 失败：{error}")
                continue
            validation = validate_chapter_split(text, chapters)
            if validation.ok:
                reusable_candidates.append(
                    (
                        (len(chapters), sum(len(chapter.body) for chapter in chapters)),
                        rule_path,
                        chapters,
                        validation,
                    )
                )
                continue
            message = f"{rule_path.name}：{'；'.join(validation.errors)}"
            failed_attempts.append(message)
            trace.append(f"{rule_path.name} 未通过校验：{'；'.join(validation.errors)}")

        if reusable_candidates:
            _, rule_path, chapters, validation = max(
                reusable_candidates,
                key=lambda item: item[0],
            )
            trace.append(f"已复用 {rule_path.name}")
            return ChapterSplitAgentResult(chapters, "rule_reused", rule_path, validation, trace)

        existing_names = [path.name for path in rule_paths]
        for reflection_index in range(1, self.max_reflections + 1):
            rule_content = self.skill.create_parser_rule(
                novel_text=text,
                failed_attempts=failed_attempts,
                existing_rule_names=existing_names,
            )
            rule, error = _chapter_rule_from_model_output(rule_content)
            if error:
                failed_attempts.append(f"第 {reflection_index} 次修正规则：{error}")
                trace.append(f"第 {reflection_index} 次修正规则失败：{error}")
                continue
            assert rule is not None
            try:
                chapters = _chapters_from_chapter_rule(rule, text)
            except ValueError as exc:
                failed_attempts.append(f"第 {reflection_index} 次修正规则：{exc}")
                trace.append(f"第 {reflection_index} 次修正规则失败：{exc}")
                continue
            validation = validate_chapter_split(text, chapters)
            if validation.ok:
                try:
                    ai_validation = self.skill.review_chapter_split(
                        novel_text=text,
                        chapters=chapters,
                        rule_content=rule_content,
                    )
                except MissingProviderCredential as exc:
                    trace.append(f"跳过 Agent 复核：{exc}")
                    ai_validation = ChapterSplitValidation(True, [])
                if not ai_validation.ok:
                    failed_attempts.append(
                        f"第 {reflection_index} 次修正规则未通过 Agent 复核："
                        f"{'；'.join(ai_validation.errors)}"
                    )
                    trace.append(
                        f"第 {reflection_index} 次修正规则未通过 Agent 复核："
                        f"{'；'.join(ai_validation.errors)}"
                    )
                    continue
                rule_path = self._save_generated_rule(rule)
                trace.append("Agent 复核通过")
                trace.append(f"第 {reflection_index} 次修正已生成 {rule_path.name}")
                return ChapterSplitAgentResult(
                    chapters,
                    "rule_created",
                    rule_path,
                    validation,
                    trace,
                )
            failed_attempts.append(
                f"第 {reflection_index} 次修正规则：{'；'.join(validation.errors)}"
            )
            trace.append(
                f"第 {reflection_index} 次修正规则未通过校验：{'；'.join(validation.errors)}"
            )

        final_validation = ChapterSplitValidation(
            False, failed_attempts or ["小说解析 Agent 执行失败"]
        )
        return ChapterSplitAgentResult([], "failed", None, final_validation, trace)

    def _run_chapter_rule_file(
        self, rule_path: Path, text: str
    ) -> tuple[list[Chapter], str | None]:
        try:
            payload = json.loads(rule_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [], f"章节规则 JSON 无效：{exc}"
        if not isinstance(payload, dict) or not isinstance(payload.get("heading_pattern"), str):
            return [], "章节规则必须包含 heading_pattern"
        rule, error = _validate_chapter_rule(
            {
                "heading_pattern": payload["heading_pattern"],
                "description": str(payload.get("description") or ""),
            }
        )
        if error:
            return [], error
        assert rule is not None
        try:
            return _chapters_from_chapter_rule(rule, text), None
        except ValueError as exc:
            return [], str(exc)

    def _save_generated_rule(self, rule: dict[str, str]) -> Path:
        serialized = json.dumps(rule, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
        rule_path = self.rules_dir / f"agent_generated_{digest}.json"
        rule_path.write_text(serialized, encoding="utf-8")
        return rule_path
