from __future__ import annotations

from datetime import datetime, timezone

from bot.diff.models import DiffResult

from .models import ApplyPlan, operation_from_change

_TARGET_PRIORITY = {
    "role": 0,
    "category": 1,
    "channel": 2,
    "overwrite": 3,
}
_ACTION_PRIORITY = {
    "Create": 0,
    "Update": 1,
    "Move": 2,
    "Reorder": 3,
    "Delete": 4,
}


def build_apply_plan(diff_result: DiffResult) -> ApplyPlan:
    ordered_changes = sorted(
        diff_result.changes,
        key=lambda change: (
            _TARGET_PRIORITY.get(change.target_type, 99),
            _ACTION_PRIORITY.get(change.action, 99),
            change.target_id or "",
        ),
    )
    operations = [operation_from_change(change, idx) for idx, change in enumerate(ordered_changes, start=1)]
    return ApplyPlan(operations=operations, created_at=datetime.now(timezone.utc))
