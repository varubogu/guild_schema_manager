from __future__ import annotations

from bot.diff.models import DiffChange, DiffResult
from bot.planner.models import ApplyReport
from bot.rendering import render_apply_report, render_diff_markdown


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


def test_render_diff_markdown_uses_spaced_table_separator() -> None:
    markdown = render_diff_markdown(
        DiffResult(
            summary={
                "Create": 1,
                "Update": 0,
                "Delete": 0,
                "Move": 0,
                "Reorder": 0,
            },
            changes=[
                DiffChange(
                    action="Create",
                    target_type="role",
                    target_id="100",
                    before=None,
                    after={"name": "Ops"},
                    risk="low",
                    before_name=None,
                    after_name="Ops",
                )
            ],
        )
    )

    assert "| --- | --- | --- | --- | --- | --- | --- | --- |" in markdown


def test_render_diff_markdown_includes_before_after_name_columns() -> None:
    markdown = render_diff_markdown(
        DiffResult(
            summary={
                "Create": 0,
                "Update": 1,
                "Delete": 0,
                "Move": 0,
                "Reorder": 0,
            },
            changes=[
                DiffChange(
                    action="Update",
                    target_type="channel",
                    target_id="300",
                    before={"topic": "old"},
                    after={"topic": "new"},
                    risk="medium",
                    before_name="一般",
                    after_name="一般",
                )
            ],
        ),
        locale="ja",
    )

    assert "| target_id | before_name | after_name |" in markdown
    assert "| 更新 | channel | 300 | 一般 | 一般 | 中 |" in markdown
