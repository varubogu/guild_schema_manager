from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import re
from typing import Any

import pytest
import yaml

from bot.commands import (
    ExportFieldSelection,
    SchemaCommandService,
    extract_uploaded_guild_id,
    overwrite_uploaded_guild_id,
)
from bot.executor import OperationExecutor
from bot.executor.noop import NoopExecutor
from bot.planner.models import ApplyOperation
from bot.schema import SchemaValidationError, parse_schema_dict, schema_to_yaml
from bot.security import AuthorizationError
from bot.session_store import InMemorySessionStore


class CountingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, operation: ApplyOperation) -> None:
        self.calls += 1
        _ = operation


class FailingExecutor:
    def execute(self, operation: ApplyOperation) -> None:
        if operation.action == "Delete":
            raise RuntimeError("delete failed")


def base_schema_dict() -> dict[str, Any]:
    return {
        "version": 1,
        "guild": {"id": "1", "name": "Guild"},
        "roles": [
            {
                "id": "100",
                "name": "Moderators",
                "permissions": ["manage_channels"],
                "position": 1,
            }
        ],
        "categories": [],
        "channels": [],
    }


def service(
    executor_factory: Callable[[], OperationExecutor] = NoopExecutor,
) -> SchemaCommandService:
    return SchemaCommandService(
        session_store=InMemorySessionStore(ttl_seconds=600),
        executor_factory=executor_factory,
    )


def schema_with_overwrites_dict() -> dict[str, Any]:
    payload = base_schema_dict()
    payload["categories"] = [
        {
            "id": "200",
            "name": "Archive",
            "position": 3,
            "overwrites": [
                {
                    "target": {"type": "role", "id": "100"},
                    "allow": ["view_channel"],
                    "deny": ["send_messages"],
                },
                {
                    "target": {"type": "member", "id": "999"},
                    "allow": [],
                    "deny": ["view_channel"],
                },
            ],
        }
    ]
    payload["channels"] = [
        {
            "id": "300",
            "name": "general",
            "type": "text",
            "parent_id": "200",
            "position": 1,
            "topic": "hello",
            "nsfw": False,
            "slowmode_delay": 5,
            "overwrites": [
                {
                    "target": {"type": "role", "id": "100"},
                    "allow": ["send_messages"],
                    "deny": [],
                },
                {
                    "target": {"type": "member", "id": "888"},
                    "allow": [],
                    "deny": ["send_messages"],
                },
            ],
        }
    ]
    return payload


def test_admin_required_for_all_commands() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = schema_to_yaml(current).encode("utf-8")
    srv = service()

    with pytest.raises(AuthorizationError):
        srv.export_schema(current, invoker_is_admin=False)

    with pytest.raises(AuthorizationError):
        srv.diff_schema(current, uploaded, invoker_is_admin=False)

    with pytest.raises(AuthorizationError):
        srv.apply_schema_preview(
            current,
            uploaded,
            invoker_is_admin=False,
            invoker_id=1,
        )


def test_export_includes_schema_hint_comment_when_url_template_is_configured() -> None:
    current = parse_schema_dict(base_schema_dict())
    srv = SchemaCommandService(
        session_store=InMemorySessionStore(ttl_seconds=600),
        executor_factory=NoopExecutor,
        schema_hint_url_template="https://schemas.example.com/schema/v{version}/schema.json",
    )

    response = srv.export_schema(current, invoker_is_admin=True)
    content = response.file.content.decode("utf-8")

    assert content.startswith(
        "# yaml-language-server: $schema="
        "https://schemas.example.com/schema/v1/schema.json"
    )


def test_export_includes_schema_hint_comment_when_fixed_url_is_configured() -> None:
    current = parse_schema_dict(base_schema_dict())
    srv = SchemaCommandService(
        session_store=InMemorySessionStore(ttl_seconds=600),
        executor_factory=NoopExecutor,
        schema_hint_url_template="https://schemas.example.com/schema/latest/schema.json",
    )

    response = srv.export_schema(current, invoker_is_admin=True)
    content = response.file.content.decode("utf-8")

    assert content.startswith(
        "# yaml-language-server: $schema="
        "https://schemas.example.com/schema/latest/schema.json"
    )


def test_export_filename_uses_guild_name_and_timestamp_format() -> None:
    current = parse_schema_dict(base_schema_dict())
    srv = service()

    response = srv.export_schema(current, invoker_is_admin=True)

    assert re.fullmatch(r"Guild-\d{8}_\d{6}\.yaml", response.file.filename)


def test_export_can_filter_fields_while_always_including_ids() -> None:
    current = parse_schema_dict(schema_with_overwrites_dict())
    srv = service()

    response = srv.export_schema(
        current,
        invoker_is_admin=True,
        fields=ExportFieldSelection(
            include_name=False,
            include_permissions=False,
            include_role_overwrites=False,
            include_other_settings=False,
        ),
    )
    exported = yaml.safe_load(response.file.content)

    assert exported["guild"] == {"id": "1"}
    assert exported["roles"] == [{"id": "100"}]
    assert exported["categories"] == [{"id": "200"}]
    assert exported["channels"] == [{"id": "300"}]
    assert "Omitted fields are treated as keep-current" in response.markdown


def test_export_uses_japanese_locale_when_requested() -> None:
    current = parse_schema_dict(base_schema_dict())
    srv = service()

    response = srv.export_schema(current, invoker_is_admin=True, locale="ja")

    assert response.markdown.startswith("エクスポート完了")


def test_export_default_includes_role_and_member_overwrites() -> None:
    current = parse_schema_dict(schema_with_overwrites_dict())
    srv = service()

    response = srv.export_schema(current, invoker_is_admin=True)
    exported = yaml.safe_load(response.file.content)

    category_overwrites = exported["categories"][0]["overwrites"]
    channel_overwrites = exported["channels"][0]["overwrites"]
    assert {item["target"]["type"] for item in category_overwrites} == {
        "role",
        "member",
    }
    assert {item["target"]["type"] for item in channel_overwrites} == {
        "role",
        "member",
    }


def test_export_role_overwrites_option_filters_to_role_targets_only() -> None:
    current = parse_schema_dict(schema_with_overwrites_dict())
    srv = service()

    response = srv.export_schema(
        current,
        invoker_is_admin=True,
        fields=ExportFieldSelection(
            include_name=False,
            include_permissions=False,
            include_role_overwrites=True,
            include_other_settings=False,
        ),
    )
    exported = yaml.safe_load(response.file.content)

    category_overwrites = exported["categories"][0]["overwrites"]
    channel_overwrites = exported["channels"][0]["overwrites"]
    assert category_overwrites == [
        {
            "target": {"type": "role", "id": "100"},
            "allow": ["view_channel"],
            "deny": ["send_messages"],
        }
    ]
    assert channel_overwrites == [
        {
            "target": {"type": "role", "id": "100"},
            "allow": ["send_messages"],
            "deny": [],
        }
    ]


def test_invoker_only_confirmation_guard() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = yaml.safe_dump(
        {"roles": [{"id": "100", "name": "Ops"}]},
        sort_keys=False,
    ).encode("utf-8")

    srv = service()
    preview = srv.apply_schema_preview(
        current,
        uploaded,
        invoker_is_admin=True,
        invoker_id=10,
    )
    assert preview.confirmation_token is not None

    response = srv.confirm_apply(
        preview.confirmation_token, invoker_id=11, current=current
    )
    assert "Only the original invoker" in response.markdown


def test_backup_is_always_produced_before_apply_execution() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = yaml.safe_dump(
        {"roles": [{"id": "100", "name": "Ops"}]},
        sort_keys=False,
    ).encode("utf-8")

    srv = service(executor_factory=NoopExecutor)
    preview = srv.apply_schema_preview(
        current,
        uploaded,
        invoker_is_admin=True,
        invoker_id=10,
    )

    response = srv.confirm_apply(
        preview.confirmation_token or "", invoker_id=10, current=current
    )
    assert response.backup_file is not None
    assert response.backup_file.filename == "guild-schema-backup.yaml"
    assert response.report is not None
    assert response.report.backup_file


def test_delete_not_executed_before_confirmation() -> None:
    current = parse_schema_dict(schema_with_overwrites_dict())
    uploaded = yaml.safe_dump(
        {
            "categories": [
                {
                    "id": "200",
                    "overwrites": [
                        {
                            "target": {"type": "role", "id": "100"},
                            "allow": ["view_channel"],
                            "deny": ["send_messages"],
                        }
                    ],
                }
            ]
        },
        sort_keys=False,
    ).encode("utf-8")

    executor = CountingExecutor()
    srv = SchemaCommandService(
        session_store=InMemorySessionStore(ttl_seconds=600),
        executor_factory=lambda: executor,
    )

    preview = srv.apply_schema_preview(
        current,
        uploaded,
        invoker_is_admin=True,
        invoker_id=10,
    )
    assert preview.confirmation_token is not None
    assert executor.calls == 0


def test_partial_failure_reporting_separates_failed_and_applied() -> None:
    current = parse_schema_dict(schema_with_overwrites_dict())
    uploaded = yaml.safe_dump(
        {
            "roles": [
                {"id": "100", "permissions": ["manage_channels", "mute_members"]}
            ],
            "categories": [
                {
                    "id": "200",
                    "overwrites": [
                        {
                            "target": {"type": "role", "id": "100"},
                            "allow": ["view_channel"],
                            "deny": ["send_messages"],
                        }
                    ],
                }
            ],
        },
        sort_keys=False,
    ).encode("utf-8")

    srv = service(executor_factory=FailingExecutor)
    preview = srv.apply_schema_preview(
        current,
        uploaded,
        invoker_is_admin=True,
        invoker_id=10,
    )

    response = srv.confirm_apply(
        preview.confirmation_token or "", invoker_id=10, current=current
    )
    assert response.report is not None
    assert len(response.report.failed) == 1
    assert len(response.report.applied) >= 1


def test_confirmation_expiry_returns_timeout_message() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = yaml.safe_dump(
        {"roles": [{"id": "100", "name": "Ops"}]},
        sort_keys=False,
    ).encode("utf-8")

    store = InMemorySessionStore(ttl_seconds=1)
    srv = SchemaCommandService(session_store=store, executor_factory=NoopExecutor)

    now = datetime.now(timezone.utc)
    preview = srv.apply_schema_preview(
        current,
        uploaded,
        invoker_is_admin=True,
        invoker_id=10,
    )
    token = preview.confirmation_token or ""

    # Simulate restart/expiry by consuming via store at future time.
    with pytest.raises(Exception):
        store.get(token, now=now + timedelta(seconds=2))

    response = srv.confirm_apply(token, invoker_id=10, current=current)
    assert (
        "expired" in response.markdown.lower()
        or "not found" in response.markdown.lower()
    )


def test_diff_partial_schema_keeps_unspecified_entities() -> None:
    current = parse_schema_dict(schema_with_overwrites_dict())
    uploaded = yaml.safe_dump(
        {"channels": [{"id": "300", "topic": "patched-topic"}]},
        sort_keys=False,
    ).encode("utf-8")

    srv = service()
    response = srv.diff_schema(current, uploaded, invoker_is_admin=True)

    assert "Update: 1" in response.markdown
    assert "Delete: 0" in response.markdown
    assert "patched-topic" in response.markdown


def test_diff_can_prefer_name_matching_when_ids_are_foreign() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = yaml.safe_dump(
        {
            "roles": [
                {
                    "id": "999",
                    "name": "Moderators",
                    "permissions": ["manage_channels", "mute_members"],
                }
            ]
        },
        sort_keys=False,
    ).encode("utf-8")

    srv = service()

    default_response = srv.diff_schema(current, uploaded, invoker_is_admin=True)
    assert "Create: 1" in default_response.markdown
    assert "Delete: 0" in default_response.markdown

    name_priority_response = srv.diff_schema(
        current,
        uploaded,
        invoker_is_admin=True,
        prefer_name_matching=True,
    )
    assert "Update: 1" in name_priority_response.markdown
    assert "Create: 0" in name_priority_response.markdown
    assert "Delete: 0" in name_priority_response.markdown


def test_diff_treats_ambiguous_channel_name_match_as_diff_not_error() -> None:
    current = parse_schema_dict(
        {
            "version": 1,
            "guild": {"id": "1", "name": "Guild"},
            "roles": [],
            "categories": [
                {"id": "200", "name": "Lobby", "position": 0, "overwrites": []}
            ],
            "channels": [
                {
                    "id": "300",
                    "name": "general",
                    "type": "text",
                    "parent_id": "200",
                    "position": 0,
                    "topic": "old-topic",
                    "overwrites": [],
                },
                {
                    "id": "301",
                    "name": "general",
                    "type": "voice",
                    "parent_id": "200",
                    "position": 1,
                    "overwrites": [],
                },
            ],
        }
    )
    uploaded = yaml.safe_dump(
        {
            "channels": [
                {"name": "general", "topic": "new-topic"},
                {"name": "news", "type": "text", "parent_name": "Lobby"},
            ]
        },
        sort_keys=False,
    ).encode("utf-8")

    srv = service()
    response = srv.diff_schema(
        current,
        uploaded,
        invoker_is_admin=True,
        prefer_name_matching=True,
    )

    assert "Update: 1" in response.markdown
    assert "Create: 1" in response.markdown
    assert "new-topic" in response.markdown


def test_diff_name_priority_matches_foreign_parent_id_channel_by_name() -> None:
    current = parse_schema_dict(
        {
            "version": 1,
            "guild": {"id": "1", "name": "Guild"},
            "roles": [
                {
                    "id": "100",
                    "name": "Moderators",
                    "permissions": ["manage_channels"],
                    "position": 1,
                }
            ],
            "categories": [
                {
                    "id": "200",
                    "name": "テキストチャンネル",
                    "position": 0,
                    "overwrites": [],
                }
            ],
            "channels": [
                {
                    "id": "300",
                    "name": "一般",
                    "type": "text",
                    "parent_id": "200",
                    "position": 0,
                    "topic": "old-topic",
                    "overwrites": [],
                }
            ],
        }
    )
    uploaded = yaml.safe_dump(
        {
            "version": 1,
            "guild": {"id": "999", "name": "Foreign Guild"},
            "roles": [
                {
                    "id": "900",
                    "name": "Moderators",
                    "permissions": ["manage_channels", "mute_members"],
                    "position": 1,
                }
            ],
            "categories": [
                {
                    "id": "800",
                    "name": "テキストチャンネル",
                    "position": 0,
                    "overwrites": [],
                }
            ],
            "channels": [
                {
                    "id": "700",
                    "name": "一般",
                    "type": "text",
                    "parent_id": "800",
                    "position": 0,
                    "topic": "patched-topic",
                    "overwrites": [],
                }
            ],
        },
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")

    srv = service()
    response = srv.diff_schema(
        current,
        uploaded,
        invoker_is_admin=True,
        prefer_name_matching=True,
    )

    assert "Create: 0" in response.markdown
    assert "Delete: 0" in response.markdown
    assert "patched-topic" in response.markdown


def test_diff_uses_japanese_labels_when_requested() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = yaml.safe_dump(
        {"roles": [{"id": "100", "name": "Ops"}]},
        sort_keys=False,
    ).encode("utf-8")

    srv = service()
    response = srv.diff_schema(current, uploaded, invoker_is_admin=True, locale="ja")

    assert "## 差分サマリー" in response.markdown
    assert "更新" in response.markdown


def test_diff_file_trust_mode_true_treats_omission_as_delete() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = yaml.safe_dump(
        {
            "version": 1,
            "guild": {"id": "1", "name": "Guild"},
            "roles": [],
            "categories": [],
            "channels": [],
        },
        sort_keys=False,
    ).encode("utf-8")

    srv = service()
    response = srv.diff_schema(
        current,
        uploaded,
        invoker_is_admin=True,
        file_trust_mode=True,
    )

    assert "Delete: 1" in response.markdown
    assert "| Delete | role | 100 |" in response.markdown


def test_apply_preview_no_changes_is_localized_for_japanese() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = schema_to_yaml(current).encode("utf-8")
    srv = service()

    preview = srv.apply_schema_preview(
        current,
        uploaded,
        invoker_is_admin=True,
        invoker_id=1,
        locale="ja",
    )

    assert preview.confirmation_token is None
    assert preview.markdown == "変更は検出されませんでした。適用対象はありません。"


def test_file_trust_mode_true_requires_full_schema() -> None:
    current = parse_schema_dict(base_schema_dict())
    uploaded = yaml.safe_dump(
        {"roles": []},
        sort_keys=False,
    ).encode("utf-8")

    srv = service()

    with pytest.raises(SchemaValidationError):
        srv.apply_schema_preview(
            current,
            uploaded,
            invoker_is_admin=True,
            invoker_id=10,
            file_trust_mode=True,
        )


def test_extract_uploaded_guild_id_returns_value_when_defined() -> None:
    uploaded = yaml.safe_dump(
        {
            "guild": {
                "id": "999",
                "name": "Other Guild",
            }
        },
        sort_keys=False,
    ).encode("utf-8")

    assert extract_uploaded_guild_id(uploaded) == "999"


def test_extract_uploaded_guild_id_returns_none_without_valid_mapping() -> None:
    uploaded_without_id = yaml.safe_dump(
        {"guild": {"name": "Other Guild"}},
        sort_keys=False,
    ).encode("utf-8")

    assert extract_uploaded_guild_id(uploaded_without_id) is None
    assert extract_uploaded_guild_id(b"- not-a-mapping") is None


def test_overwrite_uploaded_guild_id_rewrites_guild_id() -> None:
    uploaded = yaml.safe_dump(
        {
            "guild": {"id": "999", "name": "Other Guild"},
            "roles": [],
        },
        sort_keys=False,
    ).encode("utf-8")

    rewritten = overwrite_uploaded_guild_id(uploaded, "1")
    payload = yaml.safe_load(rewritten)

    assert payload["guild"]["id"] == "1"
    assert payload["guild"]["name"] == "Other Guild"
