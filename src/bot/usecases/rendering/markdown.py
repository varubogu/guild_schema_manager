from __future__ import annotations

from io import StringIO
from typing import Any
from typing import cast

from bot.localization import SupportedLocale, t
from bot.usecases.diff.models import DiffResult
from bot.usecases.planner.models import ApplyReport

_APPLY_EXCLUDED_REASON_KEY = "apply_excluded_reason"
_BOT_MANAGED_SKIP_REASON = "bot_managed_role"


def render_diff_markdown(
    diff_result: DiffResult, *, locale: SupportedLocale = "en"
) -> str:
    out = StringIO()
    summary = diff_result.summary
    action_labels = {
        "Create": t("render.action.create", locale),
        "Update": t("render.action.update", locale),
        "Delete": t("render.action.delete", locale),
        "Move": t("render.action.move", locale),
        "Reorder": t("render.action.reorder", locale),
        "UnchangedFileUndefined": t("render.action.unchanged_file_undefined", locale),
        "UnchangedExact": t("render.action.unchanged_exact", locale),
    }
    target_labels = {
        "role": t("render.target_type.role", locale),
        "category": t("render.target_type.category", locale),
        "channel": t("render.target_type.channel", locale),
        "overwrite": t("render.target_type.overwrite", locale),
    }
    risk_labels = {
        "low": t("render.risk.low", locale),
        "medium": t("render.risk.medium", locale),
        "high": t("render.risk.high", locale),
    }

    out.write(f"## {t('render.diff.title', locale)}\n")
    out.write(
        t(
            "render.diff.summary_line",
            locale,
            create_label=action_labels["Create"],
            create_count=summary["Create"],
            update_label=action_labels["Update"],
            update_count=summary["Update"],
            delete_label=action_labels["Delete"],
            delete_count=summary["Delete"],
            move_label=action_labels["Move"],
            move_count=summary["Move"],
            reorder_label=action_labels["Reorder"],
            reorder_count=summary["Reorder"],
        )
        + "\n\n"
    )

    out.write(
        f"| {t('render.diff.column.action', locale)} | "
        f"{t('render.diff.column.target_type', locale)} | "
        f"{t('render.diff.column.target_id', locale)} | "
        f"{t('render.diff.column.before_name', locale)} | "
        f"{t('render.diff.column.after_name', locale)} | "
        f"{t('render.diff.column.risk', locale)} | "
        f"{t('render.diff.column.bot_managed', locale)} | "
        f"{t('render.diff.column.before', locale)} | "
        f"{t('render.diff.column.after', locale)} |\n"
    )
    out.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for change in diff_result.changes:
        action = action_labels.get(change.action, change.action)
        target_type = target_labels.get(change.target_type, change.target_type)
        risk = risk_labels.get(change.risk, change.risk)
        bot_managed = _role_bot_managed_display(
            change.target_type,
            change.before,
            change.after,
        )
        before_payload = _payload_for_display(change.target_type, change.before)
        after_payload = _payload_for_display(change.target_type, change.after)
        before_name = _display_name(change.before_name, change.before)
        after_name = _display_name(change.after_name, change.after)
        out.write(
            f"| {action} | {target_type} | {change.target_id or '-'} | "
            f"{before_name} | {after_name} | {risk} | {bot_managed} | "
            f"`{_compact(before_payload)}` | `{_compact(after_payload)}` |\n"
        )
    for change in diff_result.informational_changes:
        action = action_labels.get(change.action, change.action)
        target_type = target_labels.get(change.target_type, change.target_type)
        bot_managed = _role_bot_managed_display(
            change.target_type,
            change.before,
            change.after,
        )
        before_payload = _payload_for_display(change.target_type, change.before)
        after_payload = _payload_for_display(change.target_type, change.after)
        before_name = _display_name(change.before_name, change.before)
        after_name = _display_name(change.after_name, change.after)
        out.write(
            f"| {action} | {target_type} | {change.target_id or '-'} | "
            f"{before_name} | {after_name} | - | {bot_managed} | "
            f"`{_compact(before_payload)}` | `{_compact(after_payload)}` |\n"
        )
    return out.getvalue().strip()


def render_apply_report(report: ApplyReport, *, locale: SupportedLocale = "en") -> str:
    out = StringIO()
    out.write(f"## {t('render.apply.title', locale)}\n")
    out.write(
        t(
            "render.apply.summary_line",
            locale,
            applied=len(report.applied),
            failed=len(report.failed),
            skipped=len(report.skipped),
        )
        + "\n\n"
    )

    if report.failed:
        out.write(f"### {t('render.apply.section.failed', locale)}\n")
        for failure in report.failed:
            out.write(
                "- "
                + t(
                    "render.apply.item.failed",
                    locale,
                    operation_id=failure["operation_id"],
                    target_type=t(
                        f"render.target_type.{failure['target_type']}", locale
                    ),
                    target_id=failure["target_id"] or "-",
                    error=failure["error"],
                )
                + "\n"
            )

    if report.skipped:
        out.write(f"\n### {t('render.apply.section.skipped', locale)}\n")
        for skipped in report.skipped:
            out.write(
                "- "
                + t(
                    "render.apply.item.skipped",
                    locale,
                    operation_id=skipped["operation_id"],
                    target_type=t(
                        f"render.target_type.{skipped['target_type']}", locale
                    ),
                    target_id=skipped["target_id"] or "-",
                    reason=skipped["reason"],
                )
                + "\n"
            )

    return out.getvalue().strip()


def _compact(value: object) -> str:
    if value is None:
        return "-"
    text = str(value)
    if len(text) > 100:
        return text[:97] + "..."
    return text


def _display_name(name: str | None, payload: object) -> str:
    if name:
        return name
    if isinstance(payload, dict):
        payload_name = cast(dict[str, object], payload).get("name")
        if isinstance(payload_name, str) and payload_name:
            return payload_name
    return "-"


def _role_bot_managed_display(
    target_type: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> str:
    if target_type != "role":
        return "-"
    return "true" if _extract_role_bot_managed(before, after) else "false"


def _extract_role_bot_managed(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> bool:
    for payload in (after, before):
        if payload is None:
            continue
        bot_managed = payload.get("bot_managed")
        if isinstance(bot_managed, bool):
            return bot_managed
        if payload.get(_APPLY_EXCLUDED_REASON_KEY) == _BOT_MANAGED_SKIP_REASON:
            return True
    return False


def _payload_for_display(
    target_type: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if payload is None:
        return None
    if target_type != "role":
        return payload

    sanitized = dict(payload)
    sanitized.pop("bot_managed", None)
    sanitized.pop(_APPLY_EXCLUDED_REASON_KEY, None)
    if not sanitized:
        return None
    return sanitized
