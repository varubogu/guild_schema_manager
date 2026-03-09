from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


DiffAction = Literal["Create", "Update", "Delete", "Move", "Reorder"]
DiffTargetType = Literal["role", "category", "channel", "overwrite"]
DiffInformationalAction = Literal["UnchangedFileUndefined", "UnchangedExact"]


def _new_diff_change_list() -> list["DiffChange"]:
    return []


def _new_diff_informational_list() -> list["DiffInformationalChange"]:
    return []


@dataclass(slots=True)
class DiffChange:
    action: DiffAction
    target_type: DiffTargetType
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    risk: Literal["low", "medium", "high"]
    before_name: str | None = None
    after_name: str | None = None


@dataclass(slots=True)
class DiffInformationalChange:
    action: DiffInformationalAction
    target_type: DiffTargetType
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    before_name: str | None = None
    after_name: str | None = None


@dataclass(slots=True)
class DiffResult:
    summary: dict[str, int]
    changes: list[DiffChange] = field(default_factory=_new_diff_change_list)
    informational_changes: list[DiffInformationalChange] = field(
        default_factory=_new_diff_informational_list
    )
