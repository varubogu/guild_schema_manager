from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bot.diff.models import DiffChange


def _new_apply_operation_list() -> list["ApplyOperation"]:
    return []


def _new_failed_item_list() -> list[dict[str, Any]]:
    return []


@dataclass(slots=True)
class ApplyOperation:
    operation_id: str
    action: str
    target_type: str
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    risk: str


@dataclass(slots=True)
class ApplyPlan:
    operations: list[ApplyOperation] = field(default_factory=_new_apply_operation_list)
    created_at: datetime | None = None


@dataclass(slots=True)
class ApplyReport:
    backup_file: bytes
    applied: list[ApplyOperation] = field(default_factory=_new_apply_operation_list)
    failed: list[dict[str, Any]] = field(default_factory=_new_failed_item_list)
    skipped: list[dict[str, Any]] = field(default_factory=_new_failed_item_list)


def operation_from_change(change: DiffChange, index: int) -> ApplyOperation:
    return ApplyOperation(
        operation_id=f"op-{index}",
        action=change.action,
        target_type=change.target_type,
        target_id=change.target_id,
        before=change.before,
        after=change.after,
        risk=change.risk,
    )
