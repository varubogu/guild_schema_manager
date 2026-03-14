from __future__ import annotations

from typing import Any

import pytest

from bot.usecases.diff import DiffValidationError, diff_schemas
from bot.usecases.schema_model import parse_schema_dict


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


def test_name_priority_matches_by_name_when_ids_differ() -> None:
    current = schema(base_payload())

    desired_payload = base_payload()
    desired_payload["roles"][0]["id"] = "999"
    desired_payload["roles"][0]["permissions"] = ["manage_channels", "mute_members"]
    desired = schema(desired_payload)

    default_result = diff_schemas(current, desired)
    assert any(
        change.action == "Create" and change.target_type == "role"
        for change in default_result.changes
    )
    assert any(
        change.action == "Delete" and change.target_type == "role"
        for change in default_result.changes
    )

    name_priority_result = diff_schemas(
        current,
        desired,
        prefer_name_matching=True,
    )
    updates = [
        c
        for c in name_priority_result.changes
        if c.action == "Update" and c.target_type == "role"
    ]
    assert len(updates) == 1
    assert name_priority_result.summary["Create"] == 0
    assert name_priority_result.summary["Delete"] == 0


def test_bot_managed_role_update_is_marked_apply_excluded() -> None:
    current_payload = base_payload()
    current_payload["roles"][0]["bot_managed"] = True
    current = schema(current_payload)

    desired_payload = base_payload()
    desired_payload["roles"][0]["bot_managed"] = True
    desired_payload["roles"][0]["permissions"] = ["manage_channels", "mute_members"]
    desired = schema(desired_payload)

    result = diff_schemas(current, desired)

    updates = [
        change
        for change in result.changes
        if change.action == "Update" and change.target_type == "role"
    ]
    assert len(updates) == 1
    assert updates[0].before is not None
    assert updates[0].after is not None
    assert updates[0].before["apply_excluded_reason"] == "bot_managed_role"
    assert updates[0].after["apply_excluded_reason"] == "bot_managed_role"


def test_bot_managed_only_difference_is_not_treated_as_update() -> None:
    current_payload = base_payload()
    current_payload["roles"][0]["bot_managed"] = False
    current = schema(current_payload)

    desired_payload = base_payload()
    desired_payload["roles"][0]["bot_managed"] = True
    desired = schema(desired_payload)

    result = diff_schemas(current, desired)

    updates = [
        change
        for change in result.changes
        if change.action == "Update" and change.target_type == "role"
    ]
    assert updates == []


def test_name_priority_does_not_fallback_to_id_for_all_entities() -> None:
    current = schema(base_payload())

    desired_payload = base_payload()
    desired_payload["roles"][0]["name"] = "Ops"
    desired_payload["categories"][0]["name"] = "Archive"
    desired_payload["channels"][0]["name"] = "general"
    desired_payload["channels"][0]["parent_id"] = "200"
    desired = schema(desired_payload)

    result = diff_schemas(current, desired, prefer_name_matching=True)

    assert any(c.action == "Create" and c.target_type == "role" for c in result.changes)
    assert any(c.action == "Delete" and c.target_type == "role" for c in result.changes)
    assert any(
        c.action == "Create" and c.target_type == "category" for c in result.changes
    )
    assert any(
        c.action == "Delete" and c.target_type == "category" for c in result.changes
    )
    assert any(
        c.action == "Create" and c.target_type == "channel" for c in result.changes
    )
    assert any(
        c.action == "Delete" and c.target_type == "channel" for c in result.changes
    )


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


def test_name_only_duplicate_match_reports_multiple_errors() -> None:
    current_payload = base_payload()
    current_payload["roles"] = [
        {"name": "Same", "permissions": []},
        {"name": "Same", "permissions": []},
    ]
    current = schema(current_payload)

    desired_payload = base_payload()
    desired_payload["roles"] = [
        {"name": "Same", "permissions": ["manage_channels"]},
        {"name": "Same", "permissions": ["mute_members"]},
    ]
    desired = schema(desired_payload)

    with pytest.raises(DiffValidationError) as exc:
        diff_schemas(current, desired)

    assert str(exc.value).count("name-only duplicate match in role: 'Same'") == 2


def test_name_only_duplicate_match_can_be_treated_as_unmatched() -> None:
    current_payload = base_payload()
    current_payload["roles"] = [
        {"name": "Same", "permissions": []},
        {"name": "Same", "permissions": []},
    ]
    current = schema(current_payload)

    desired_payload = base_payload()
    desired_payload["roles"] = [{"name": "Same", "permissions": ["manage_channels"]}]
    desired = schema(desired_payload)

    result = diff_schemas(current, desired, allow_ambiguous_name_match=True)

    assert result.summary["Update"] == 1
    assert result.summary["Delete"] == 1


def test_role_name_match_prefers_same_bot_managed_candidate() -> None:
    current_payload = base_payload()
    current_payload["roles"] = [
        {"id": "100", "name": "SameName", "bot_managed": False, "permissions": []},
        {"id": "101", "name": "SameName", "bot_managed": True, "permissions": []},
    ]
    current = schema(current_payload)

    desired_payload = base_payload()
    desired_payload["roles"] = [
        {
            "id": "999",
            "name": "SameName",
            "bot_managed": True,
            "permissions": ["manage_channels"],
        }
    ]
    desired = schema(desired_payload)

    result = diff_schemas(current, desired, prefer_name_matching=True)
    updates = [
        change
        for change in result.changes
        if change.action == "Update" and change.target_type == "role"
    ]
    assert len(updates) == 1
    assert updates[0].target_id == "101"


def test_channel_name_match_uses_parent_and_type_scope() -> None:
    current_payload = base_payload()
    current_payload["categories"] = [
        {"id": "200", "name": "A", "position": 0, "overwrites": []},
        {"id": "201", "name": "B", "position": 1, "overwrites": []},
    ]
    current_payload["channels"] = [
        {
            "name": "general",
            "type": "text",
            "parent_id": "200",
            "topic": "topic-a",
            "overwrites": [],
        },
        {
            "name": "general",
            "type": "text",
            "parent_id": "201",
            "topic": "topic-b",
            "overwrites": [],
        },
    ]
    current = schema(current_payload)

    desired_payload = base_payload()
    desired_payload["categories"] = current_payload["categories"]
    desired_payload["channels"] = [
        {
            "name": "general",
            "type": "text",
            "parent_id": "200",
            "topic": "patched-a",
            "overwrites": [],
        },
        {
            "name": "general",
            "type": "text",
            "parent_id": "201",
            "topic": "topic-b",
            "overwrites": [],
        },
    ]
    desired = schema(desired_payload)

    result = diff_schemas(current, desired)

    updates = [
        c for c in result.changes if c.action == "Update" and c.target_type == "channel"
    ]
    assert len(updates) == 1
    assert updates[0].after == {"topic": "patched-a"}


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
