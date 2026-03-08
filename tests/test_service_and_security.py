from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import yaml

from bot.commands import ExportFieldSelection, SchemaCommandService
from bot.executor import OperationExecutor
from bot.executor.noop import NoopExecutor
from bot.planner.models import ApplyOperation
from bot.schema import parse_schema_dict, schema_to_yaml
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


def test_export_includes_schema_hint_comment_when_repo_is_configured() -> None:
    current = parse_schema_dict(base_schema_dict())
    srv = SchemaCommandService(
        session_store=InMemorySessionStore(ttl_seconds=600),
        executor_factory=NoopExecutor,
        schema_repo_owner="example-org",
        schema_repo_name="guild-schema-manager",
    )

    response = srv.export_schema(current, invoker_is_admin=True)
    content = response.file.content.decode("utf-8")

    assert content.startswith(
        "# yaml-language-server: $schema="
        "https://example-org.github.io/guild-schema-manager/schema/v1/schema.json"
    )


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
    assert "filtered exports may fail validation" in response.markdown


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
    desired = base_schema_dict()
    desired["roles"] = []
    uploaded = schema_to_yaml(parse_schema_dict(desired)).encode("utf-8")

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
    desired = base_schema_dict()
    desired["roles"] = []
    uploaded = schema_to_yaml(parse_schema_dict(desired)).encode("utf-8")

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
    current = parse_schema_dict(base_schema_dict())
    desired = base_schema_dict()
    desired["roles"] = []
    uploaded = schema_to_yaml(parse_schema_dict(desired)).encode("utf-8")

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
    current = parse_schema_dict(base_schema_dict())
    desired = base_schema_dict()
    desired["roles"] = []
    desired["categories"] = [{"id": "200", "name": "New Cat", "overwrites": []}]
    uploaded = schema_to_yaml(parse_schema_dict(desired)).encode("utf-8")

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
    desired = base_schema_dict()
    desired["roles"] = []
    uploaded = schema_to_yaml(parse_schema_dict(desired)).encode("utf-8")

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
