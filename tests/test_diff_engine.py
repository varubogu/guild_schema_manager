from __future__ import annotations

from typing import Any

import pytest

from bot.diff import DiffValidationError, diff_schemas
from bot.schema import parse_schema_dict


def schema(payload: dict[str, Any]):
    return parse_schema_dict(payload)


def base_payload() -> dict[str, Any]:
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
        "categories": [
            {
                "id": "200",
                "name": "Info",
                "position": 0,
                "overwrites": [],
            }
        ],
        "channels": [
            {
                "id": "300",
                "name": "announcements",
                "type": "text",
                "parent_id": "200",
                "position": 0,
                "topic": "hello",
                "overwrites": [],
            }
        ],
    }


def test_id_first_rename_detected_as_update() -> None:
    current = schema(base_payload())
    desired_payload = base_payload()
    desired_payload["roles"][0]["name"] = "New Moderators"

    result = diff_schemas(current, schema(desired_payload))

    updates = [
        c for c in result.changes if c.action == "Update" and c.target_type == "role"
    ]
    assert len(updates) == 1
    assert updates[0].before == {"name": "Moderators"}
    assert updates[0].after == {"name": "New Moderators"}


def test_name_only_unique_match_updates_existing() -> None:
    payload = base_payload()
    payload["roles"] = [{"name": "Moderators", "permissions": ["manage_channels"]}]
    current = schema(payload)

    desired_payload = base_payload()
    desired_payload["roles"] = [
        {"name": "Moderators", "permissions": ["manage_channels", "mute_members"]}
    ]
    desired = schema(desired_payload)

    result = diff_schemas(current, desired)

    updates = [
        c for c in result.changes if c.action == "Update" and c.target_type == "role"
    ]
    assert len(updates) == 1
    before = updates[0].before
    after = updates[0].after
    assert before is not None
    assert after is not None
    assert before["permissions"] == ["manage_channels"]
    assert after["permissions"] == ["manage_channels", "mute_members"]


def test_name_only_duplicate_match_raises_error() -> None:
    current_payload = base_payload()
    current_payload["roles"] = [
        {"name": "Same", "permissions": []},
        {"name": "Same", "permissions": []},
    ]
    current = schema(current_payload)

    desired_payload = base_payload()
    desired_payload["roles"] = [{"name": "Same", "permissions": ["manage_channels"]}]
    desired = schema(desired_payload)

    with pytest.raises(DiffValidationError):
        diff_schemas(current, desired)


def test_overwrite_add_update_delete_diff_detected() -> None:
    current_payload = base_payload()
    current_payload["categories"][0]["overwrites"] = [
        {
            "target": {"type": "role", "id": "100"},
            "allow": ["view_channel"],
            "deny": [],
        }
    ]
    current = schema(current_payload)

    desired_payload = base_payload()
    desired_payload["categories"][0]["overwrites"] = [
        {
            "target": {"type": "role", "id": "100"},
            "allow": ["view_channel", "send_messages"],
            "deny": [],
        },
        {
            "target": {"type": "member", "id": "999"},
            "allow": ["view_channel"],
            "deny": [],
        },
    ]
    desired = schema(desired_payload)

    result = diff_schemas(current, desired)

    overwrite_changes = [c for c in result.changes if c.target_type == "overwrite"]
    assert any(c.action == "Update" for c in overwrite_changes)
    assert any(c.action == "Create" for c in overwrite_changes)


def test_parent_move_and_reorder_detected() -> None:
    current = schema(base_payload())
    desired_payload = base_payload()
    desired_payload["channels"][0]["parent_id"] = None
    desired_payload["channels"][0]["position"] = 2

    result = diff_schemas(current, schema(desired_payload))

    assert any(
        c.action == "Move" and c.target_type == "channel" for c in result.changes
    )
    assert any(
        c.action == "Reorder" and c.target_type == "channel" for c in result.changes
    )
