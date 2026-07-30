from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    script_path: Path | None
    validation: ChapterSplitValidation
    trace: list[str]


def validate_chapter_split(text: str, chapters: list[Chapter]) -> ChapterSplitValidation:
    errors: list[str] = []
    if not chapters:
        errors.append("no chapters returned")
        return ChapterSplitValidation(False, errors)

    for index, chapter in enumerate(chapters, start=1):
        expected_id = f"chapter-{index:04d}"
        if chapter.chapter_id != expected_id:
            errors.append(f"chapter id mismatch: expected {expected_id}, got {chapter.chapter_id}")
        if not chapter.title.strip():
            errors.append(f"{chapter.chapter_id} has empty title")
        if not chapter.body.strip():
            errors.append(f"{chapter.chapter_id} has empty body")

    if len(chapters) == 1 and _repeated_heading_like_lines(text) >= 2:
        errors.append("single chapter result but repeated heading-like lines were found")

    source_nonspace = re.sub(r"\s+", "", text)
    body_nonspace = re.sub(r"\s+", "", "".join(chapter.body for chapter in chapters))
    if len(source_nonspace) >= 80 and len(body_nonspace) < int(len(source_nonspace) * 0.25):
        errors.append("chapter bodies cover too little of the source text")

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
        raise TypeError("parser output must be a list or an object with chapters")

    chapters: list[Chapter] = []
    for index, item in enumerate(raw_chapters, start=1):
        if not isinstance(item, dict):
            raise TypeError("chapter item must be an object")
        chapters.append(
            Chapter(
                chapter_id=str(item.get("chapter_id") or f"chapter-{index:04d}"),
                title=str(item.get("title") or "").strip(),
                body=str(item.get("body") or "").strip(),
            )
        )
    return chapters


def _strip_python_fence(content: str) -> str:
    cleaned = content.strip()
    fenced = re.search(r"```(?:python)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else cleaned


def _strip_json_fence(content: str) -> str:
    cleaned = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else cleaned


class ChapterSplitSkill:
    def __init__(
        self,
        *,
        provider: dict[str, Any] | None = None,
        api_key_lookup: ApiKeyLookup | None = None,
    ):
        self.provider = provider or {
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "api_key_env": "DEEPSEEK_API_KEY",
            "timeout_seconds": 120,
        }
        self.api_key_lookup = api_key_lookup or (lambda name: None)

    def _chat_model(self):
        provider = getattr(self, "provider", None) or {}
        api_key_lookup = getattr(self, "api_key_lookup", lambda name: None)
        api_key_env = str(provider.get("api_key_env") or "DEEPSEEK_API_KEY")
        api_key = api_key_lookup(api_key_env)
        if not api_key:
            raise MissingProviderCredential(f"Missing API key environment variable: {api_key_env}")

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=api_key,
            base_url=str(provider.get("base_url") or "https://api.deepseek.com"),
            model=str(provider.get("model") or "deepseek-v4-flash"),
            temperature=0,
            timeout=int(provider.get("timeout_seconds", 120)),
        )

    def create_parser_script(
        self,
        *,
        novel_text: str,
        failed_attempts: list[str],
        existing_script_names: list[str],
    ) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = self._chat_model()
        messages = [
            SystemMessage(
                content=(
                    "你是 NovelVoice-Agent 的章节划分脚本生成 skill。"
                    "你只返回可直接运行的 Python 脚本，不返回 Markdown 解释。"
                )
            ),
            HumanMessage(content=self._build_prompt(novel_text, failed_attempts, existing_script_names)),
        ]
        response = llm.invoke(messages)
        return _strip_python_fence(str(response.content))

    def review_chapter_split(
        self,
        *,
        novel_text: str,
        chapters: list[Chapter],
        script_content: str,
    ) -> ChapterSplitValidation:
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = self._chat_model()
        messages = [
            SystemMessage(
                content=(
                    "你是 NovelVoice-Agent 的章节划分结果检查 agent。"
                    "你只返回 JSON，不返回 Markdown。"
                )
            ),
            HumanMessage(content=self._build_review_prompt(novel_text, chapters, script_content)),
        ]
        response = llm.invoke(messages)
        try:
            payload = json.loads(_strip_json_fence(str(response.content)))
        except json.JSONDecodeError as exc:
            return ChapterSplitValidation(False, [f"AI validation returned invalid JSON: {exc}"])
        if not isinstance(payload, dict):
            return ChapterSplitValidation(False, ["AI validation output must be an object"])
        raw_errors = payload.get("errors", [])
        errors = [str(item) for item in raw_errors] if isinstance(raw_errors, list) else []
        ok = bool(payload.get("ok")) and not errors
        return ChapterSplitValidation(ok, errors or ([] if ok else ["AI validation rejected result"]))

    def _build_prompt(
        self,
        novel_text: str,
        failed_attempts: list[str],
        existing_script_names: list[str],
    ) -> str:
        sample = novel_text[:12000]
        failed = "\n".join(f"- {item}" for item in failed_attempts[-6:]) or "- 无"
        scripts = ", ".join(existing_script_names) or "无"
        return f"""
请观察上传 txt 小说开头若干章格式，创建一个章节划分 Python 脚本。

脚本要求：
- 从 stdin 读取完整小说文本。
- 输出严格 JSON：{{"chapters":[{{"chapter_id":"chapter-0001","title":"标题","body":"正文"}}]}}。
- chapter_id 必须从 chapter-0001 递增。
- title 是章节标题行，body 是该章节标题之后到下一章标题之前的正文。
- 必须包含中文注释，说明“这是划分什么格式的”。
- 不要调用网络、不要读写文件、不要依赖第三方包。
- 返回纯 Python 代码，不要 Markdown 代码围栏。

已有脚本：{scripts}
失败结果（reflection 输入，避免重复错误）：
{failed}

小说样本：
{sample}
""".strip()

    def _build_review_prompt(
        self,
        novel_text: str,
        chapters: list[Chapter],
        script_content: str,
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

脚本：
{script_content[:6000]}

章节摘要：
{json.dumps(chapter_summary, ensure_ascii=False)}
""".strip()


class AiChapterSplitAgent:
    def __init__(
        self,
        *,
        scripts_dir: Path,
        skill: ChapterSplitSkill,
        timeout_seconds: int = 8,
        max_reflections: int = 2,
    ):
        self.scripts_dir = scripts_dir
        self.skill = skill
        self.timeout_seconds = timeout_seconds
        self.max_reflections = max_reflections

    def split(self, text: str) -> ChapterSplitAgentResult:
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        trace: list[str] = []
        failed_attempts: list[str] = []

        scripts = sorted(path for path in self.scripts_dir.glob("*.py") if path.is_file())
        for script_path in scripts:
            chapters, error = self._run_script(script_path, text)
            if error:
                failed_attempts.append(f"{script_path.name}: {error}")
                trace.append(f"{script_path.name} failed: {error}")
                continue
            validation = validate_chapter_split(text, chapters)
            if validation.ok:
                trace.append(f"{script_path.name} reused")
                return ChapterSplitAgentResult(chapters, "script_reused", script_path, validation, trace)
            message = f"{script_path.name}: {'; '.join(validation.errors)}"
            failed_attempts.append(message)
            trace.append(f"{script_path.name} rejected: {'; '.join(validation.errors)}")

        existing_names = [script.name for script in scripts]
        for reflection_index in range(1, self.max_reflections + 1):
            script_content = self.skill.create_parser_script(
                novel_text=text,
                failed_attempts=failed_attempts,
                existing_script_names=existing_names,
            )
            script_path = self._save_generated_script(script_content)
            chapters, error = self._run_script(script_path, text)
            if error:
                failed_attempts.append(f"{script_path.name}: {error}")
                trace.append(f"reflection {reflection_index} failed: {error}")
                continue
            validation = validate_chapter_split(text, chapters)
            if validation.ok:
                try:
                    ai_validation = self.skill.review_chapter_split(
                        novel_text=text,
                        chapters=chapters,
                        script_content=script_content,
                    )
                except MissingProviderCredential as exc:
                    trace.append(f"AI validation skipped: {exc}")
                    ai_validation = ChapterSplitValidation(True, [])
                if not ai_validation.ok:
                    failed_attempts.append(
                        f"{script_path.name}: AI validation rejected: "
                        f"{'; '.join(ai_validation.errors)}"
                    )
                    trace.append(
                        f"reflection {reflection_index} AI rejected: "
                        f"{'; '.join(ai_validation.errors)}"
                    )
                    continue
                trace.append("AI validation accepted")
                trace.append(f"reflection {reflection_index} created {script_path.name}")
                return ChapterSplitAgentResult(
                    chapters,
                    "script_created",
                    script_path,
                    validation,
                    trace,
                )
            failed_attempts.append(f"{script_path.name}: {'; '.join(validation.errors)}")
            trace.append(f"reflection {reflection_index} rejected: {'; '.join(validation.errors)}")

        final_validation = ChapterSplitValidation(False, failed_attempts or ["agent failed"])
        return ChapterSplitAgentResult([], "failed", None, final_validation, trace)

    def _run_script(self, script_path: Path, text: str) -> tuple[list[Chapter], str | None]:
        try:
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                input=text,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return [], str(exc)
        if completed.returncode != 0:
            return [], completed.stderr.strip() or f"exit code {completed.returncode}"
        try:
            return _chapters_from_payload(json.loads(completed.stdout)), None
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return [], f"invalid JSON output: {exc}"

    def _save_generated_script(self, script_content: str) -> Path:
        cleaned = _strip_python_fence(script_content)
        if "划分" not in cleaned[:300]:
            cleaned = "# AI生成脚本：划分自动识别的章节标题格式\n" + cleaned
        digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]
        script_path = self.scripts_dir / f"agent_generated_{digest}.py"
        script_path.write_text(cleaned.rstrip() + "\n", encoding="utf-8")
        return script_path
