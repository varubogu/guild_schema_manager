from __future__ import annotations

from io import StringIO

from bot.diff.models import DiffResult
from bot.planner.models import ApplyReport


def render_diff_markdown(diff_result: DiffResult) -> str:
    out = StringIO()
    summary = diff_result.summary
    out.write("## Diff Summary\n")
    out.write(
        f"Create: {summary['Create']}, Update: {summary['Update']}, Delete: {summary['Delete']}, "
        f"Move: {summary['Move']}, Reorder: {summary['Reorder']}\n\n"
    )

    out.write("| action | target_type | target_id | risk | before | after |\n")
    out.write("|---|---|---|---|---|---|\n")
    for change in diff_result.changes:
        out.write(
            f"| {change.action} | {change.target_type} | {change.target_id or '-'} | {change.risk} | "
            f"`{_compact(change.before)}` | `{_compact(change.after)}` |\n"
        )
    return out.getvalue().strip()


def render_apply_report(report: ApplyReport) -> str:
    out = StringIO()
    out.write("## Apply Result\n")
    out.write(
        f"applied: {len(report.applied)}, failed: {len(report.failed)}, skipped: {len(report.skipped)}\n\n"
    )

    if report.failed:
        out.write("### Failed\n")
        for failure in report.failed:
            out.write(
                f"- {failure['operation_id']} {failure['target_type']}({failure['target_id']}) "
                f"error={failure['error']}\n"
            )

    if report.skipped:
        out.write("\n### Skipped\n")
        for skipped in report.skipped:
            out.write(
                f"- {skipped['operation_id']} {skipped['target_type']}({skipped['target_id']}) "
                f"reason={skipped['reason']}\n"
            )

    return out.getvalue().strip()


def _compact(value: object) -> str:
    if value is None:
        return "-"
    text = str(value)
    if len(text) > 100:
        return text[:97] + "..."
    return text
