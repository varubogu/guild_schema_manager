from __future__ import annotations

from bot.planner.models import ApplyReport
from bot.rendering import render_apply_report


def test_render_apply_report_includes_skipped_section() -> None:
    report = ApplyReport(
        backup_file=b"backup",
        failed=[
            {
                "operation_id": "op-2",
                "target_type": "channel",
                "target_id": "200",
                "error": "boom",
            }
        ],
        skipped=[
            {
                "operation_id": "op-3",
                "target_type": "role",
                "target_id": "300",
                "reason": "manual cleanup",
            }
        ],
    )

    markdown = render_apply_report(report)

    assert "### Failed" in markdown
    assert "### Skipped" in markdown
    assert "manual cleanup" in markdown


def test_render_apply_report_localizes_headings_for_japanese() -> None:
    report = ApplyReport(
        backup_file=b"backup",
        failed=[],
        skipped=[],
    )

    markdown = render_apply_report(report, locale="ja")

    assert "## 適用結果" in markdown
