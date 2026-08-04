from __future__ import annotations

import math
import re
from typing import Any

DEFAULT_CONTEXT_WINDOW = 32768
DEFAULT_RESERVED_OUTPUT_TOKENS = 1024


def estimate_text_tokens(text: str, *, chinese_chars_per_token: float = 1.7) -> int:
    """Estimate tokens without a provider-specific tokenizer.

    Chinese text is approximated by character density; non-CJK text uses a rough
    four-characters-per-token heuristic. This is intentionally conservative and
    replaceable by a real tokenizer later.
    """
    if not text:
        return 0
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return 0
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", compact))
    non_cjk_count = len(compact) - cjk_count
    return max(1, math.ceil(cjk_count / chinese_chars_per_token + non_cjk_count / 4))


def build_token_context_report(
    *,
    system_prompt: str,
    input_text: str,
    output_text: str = "",
    context_window: int = DEFAULT_CONTEXT_WINDOW,
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS,
    rag_evidence_tokens: int = 0,
) -> dict[str, Any]:
    prompt_tokens = estimate_text_tokens(system_prompt)
    input_tokens = estimate_text_tokens(input_text)
    output_tokens = estimate_text_tokens(output_text)
    total_tokens = prompt_tokens + input_tokens + output_tokens + max(0, rag_evidence_tokens)
    available_input_tokens = max(0, context_window - reserved_output_tokens - prompt_tokens)
    return {
        "strategy": "heuristic_cjk_1_7_chars_per_token",
        "estimated_prompt_tokens": prompt_tokens,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "rag_evidence_tokens": max(0, rag_evidence_tokens),
        "estimated_total_tokens": total_tokens,
        "context_window": context_window,
        "reserved_output_tokens": reserved_output_tokens,
        "available_input_tokens": available_input_tokens,
        "within_context_window": total_tokens + reserved_output_tokens <= context_window,
        "budget_policy": {
            "system_prompt": "preserve",
            "current_chapter": "prioritize",
            "current_paragraph": "prioritize",
            "role_list": "compress_when_over_budget",
            "rag_evidence": "cap",
            "output_tokens": "reserve",
        },
    }


def summarize_for_trace(text: str, *, max_chars: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()}…"
