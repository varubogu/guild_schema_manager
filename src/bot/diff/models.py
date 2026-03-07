from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


DiffAction = Literal["Create", "Update", "Delete", "Move", "Reorder"]
DiffTargetType = Literal["role", "category", "channel", "overwrite"]


def _new_diff_change_list() -> list["DiffChange"]:
    return []


@dataclass(slots=True)
class DiffChange:
    action: DiffAction
    target_type: DiffTargetType
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    risk: Literal["low", "medium", "high"]


@dataclass(slots=True)
class DiffResult:
    summary: dict[str, int]
    changes: list[DiffChange] = field(default_factory=_new_diff_change_list)
