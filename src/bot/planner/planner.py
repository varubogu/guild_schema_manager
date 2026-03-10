from __future__ import annotations

from typing import Any

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
_APPLY_EXCLUDED_REASON_KEY = "apply_excluded_reason"
_BOT_MANAGED_SKIP_REASON = "bot_managed_role"


def build_apply_plan(diff_result: DiffResult) -> ApplyPlan:
    ordered_changes = sorted(
        diff_result.changes,
        key=lambda change: (
            _TARGET_PRIORITY.get(change.target_type, 99),
            _ACTION_PRIORITY.get(change.action, 99),
            change.target_id or "",
        ),
    )
    operations = [
        operation_from_change(
            change,
            idx,
            skip_reason=_skip_reason_for_change(
                change.before, change.after, change.target_type
            ),
        )
        for idx, change in enumerate(ordered_changes, start=1)
    ]
    return ApplyPlan(operations=operations, created_at=datetime.now(timezone.utc))


def _skip_reason_for_change(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    target_type: str,
) -> str | None:
    if target_type != "role":
        return None
    if _payload_is_bot_managed(before) or _payload_is_bot_managed(after):
        return _BOT_MANAGED_SKIP_REASON
    return None


def _payload_is_bot_managed(payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return False
    explicit_reason = payload.get(_APPLY_EXCLUDED_REASON_KEY)
    if explicit_reason == _BOT_MANAGED_SKIP_REASON:
        return True
    return bool(payload.get("bot_managed"))
