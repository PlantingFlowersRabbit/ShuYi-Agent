from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

SelectionItem = dict[str, Any]
BatchSelector = Callable[[list[SelectionItem]], list[SelectionItem]]


@dataclass(frozen=True)
class BoundedSelectionResult:
    status: str
    rounds: int
    resolved: list[SelectionItem]
    unresolved: list[SelectionItem]


def run_bounded_selection(
    *,
    items: list[SelectionItem],
    select_batch: BatchSelector,
    batch_size: int,
    max_rounds: int,
) -> BoundedSelectionResult:
    if batch_size < 1:
        raise ValueError("批量大小至少为 1")
    if max_rounds < 0:
        raise ValueError("最大轮次不能为负数")

    unresolved = list(items)
    resolved: list[SelectionItem] = []
    cursor = 0
    rounds = 0

    while unresolved and rounds < max_rounds:
        start = cursor % len(unresolved)
        batch = (unresolved + unresolved)[start : start + min(batch_size, len(unresolved))]
        selections = select_batch(list(batch)) or []
        rounds += 1

        selected_ids = {
            str(item["statement_id"])
            for item in selections
            if isinstance(item, dict) and item.get("statement_id") is not None
        }
        batch_ids = {str(item.get("statement_id")) for item in batch}
        accepted_ids = selected_ids & batch_ids
        if accepted_ids:
            resolved.extend(
                item
                for item in selections
                if isinstance(item, dict) and str(item.get("statement_id")) in accepted_ids
            )
            unresolved = [
                item for item in unresolved if str(item.get("statement_id")) not in accepted_ids
            ]
            cursor = 0 if not unresolved else start % len(unresolved)
        else:
            cursor = (start + len(batch)) % len(unresolved)

    return BoundedSelectionResult(
        status="completed" if not unresolved else "exhausted",
        rounds=rounds,
        resolved=resolved,
        unresolved=unresolved,
    )
