from __future__ import annotations

from bot.usecases.diff.models import DiffChange, DiffInformationalChange, DiffResult
from bot.usecases.planner.models import ApplyReport
from bot.usecases.rendering import render_apply_report, render_diff_markdown


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

    assert (
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
        in markdown
    )


def test_render_diff_markdown_includes_current_config_applied_name_columns() -> None:
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

    assert (
        "| target_id | 現在サーバー名 | 構成ファイル名 | 適用後名 | risk | "
        "botが管理している項目 |" in markdown
    )
    assert "| 更新 | channel | 300 | 一般 | - | 一般 | 中 | - |" in markdown


def test_render_diff_markdown_renders_config_columns() -> None:
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
                    config={"topic": "from-file"},
                    after={"topic": "new"},
                    risk="medium",
                    before_name="general",
                    config_name="general",
                    after_name="general",
                )
            ],
        ),
    )

    assert "| current_server_name | config_file_name | applied_name |" in markdown
    assert (
        "`{'topic': 'old'}` | `{'topic': 'from-file'}` | `{'topic': 'new'}`" in markdown
    )


def test_render_diff_markdown_renders_informational_rows() -> None:
    markdown = render_diff_markdown(
        DiffResult(
            summary={
                "Create": 0,
                "Update": 0,
                "Delete": 0,
                "Move": 0,
                "Reorder": 0,
            },
            changes=[],
            informational_changes=[
                DiffInformationalChange(
                    action="UnchangedFileUndefined",
                    target_type="role",
                    target_id="100",
                    before={"name": "Moderators"},
                    after={"name": "Moderators"},
                    before_name="Moderators",
                    after_name="Moderators",
                )
            ],
        )
    )

    assert "No change (undefined in file)" in markdown
    assert "| role | 100 | Moderators | - | Moderators | - | false |" in markdown


def test_render_diff_markdown_hides_internal_apply_excluded_fields() -> None:
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
                    target_type="role",
                    target_id="100",
                    before={
                        "permissions": ["manage_channels"],
                        "bot_managed": True,
                        "apply_excluded_reason": "bot_managed_role",
                    },
                    after={
                        "permissions": ["manage_channels", "mute_members"],
                        "bot_managed": True,
                        "apply_excluded_reason": "bot_managed_role",
                    },
                    risk="medium",
                    before_name="BotRole",
                    after_name="BotRole",
                )
            ],
        )
    )

    assert "apply_excluded_reason" not in markdown
    assert "'bot_managed': True" not in markdown
    assert "| Update | role | 100 | BotRole | - | BotRole | medium | true |" in markdown
    assert "bot_managed_role" in markdown
    assert (
        "`{'permissions': ['manage_channels']}` | `-` | "
        "`{'permissions': ['manage_channels']}`"
    ) in markdown


def test_render_diff_markdown_includes_apply_skip_reason_column() -> None:
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
                    target_type="role",
                    target_id="100",
                    before={"name": "Moderators"},
                    after={"name": "Moderators2"},
                    risk="medium",
                    before_name="Moderators",
                    after_name="Moderators2",
                )
            ],
        ),
        expected_skip_reasons=["role_hierarchy_restriction"],
    )

    assert "apply_skip_reason" in markdown
    assert "role_hierarchy_restriction" in markdown
    assert "`{'name': 'Moderators'}` | `-` | `{'name': 'Moderators'}`" in markdown
