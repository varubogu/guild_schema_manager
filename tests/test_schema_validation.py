from __future__ import annotations

from typing import Any

import pytest
import yaml

from bot.schema import (
    SchemaValidationError,
    parse_schema_dict,
    parse_schema_patch_yaml,
    schema_to_yaml,
)


def base_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "guild": {"id": "1", "name": "Guild"},
        "roles": [
            {
                "id": "10",
                "name": "Mod",
                "permissions": ["manage_channels"],
            }
        ],
        "categories": [],
        "channels": [
            {
                "id": "20",
                "name": "general",
                "type": "text",
                "overwrites": [],
            }
        ],
    }


def test_unknown_top_level_key_rejected() -> None:
    payload = base_payload()
    payload["unexpected"] = True

    with pytest.raises(SchemaValidationError) as exc:
        parse_schema_dict(payload)

    assert "unknown keys" in str(exc.value)


def test_unsupported_channel_type_rejected() -> None:
    payload = base_payload()
    payload["channels"][0]["type"] = "unsupported"

    with pytest.raises(SchemaValidationError) as exc:
        parse_schema_dict(payload)

    assert "unsupported channel type" in str(exc.value)


def test_duplicate_role_ids_rejected() -> None:
    payload = base_payload()
    payload["roles"].append({"id": "10", "name": "Another"})

    with pytest.raises(SchemaValidationError) as exc:
        parse_schema_dict(payload)

    assert "duplicate explicit IDs" in str(exc.value)


def test_role_bot_managed_accepts_boolean() -> None:
    payload = base_payload()
    payload["roles"][0]["bot_managed"] = True

    parsed = parse_schema_dict(payload)

    assert parsed.roles[0].bot_managed is True


def test_role_bot_managed_rejects_non_boolean() -> None:
    payload = base_payload()
    payload["roles"][0]["bot_managed"] = "yes"

    with pytest.raises(SchemaValidationError) as exc:
        parse_schema_dict(payload)

    assert "roles[0].bot_managed" in str(exc.value)


def test_schema_to_yaml_preserves_japanese_characters() -> None:
    payload = base_payload()
    payload["guild"]["name"] = "日本語サーバー"
    payload["channels"][0]["name"] = "テキストチャンネル"
    schema = parse_schema_dict(payload)

    exported = schema_to_yaml(schema)

    assert "テキストチャンネル" in exported
    assert r"\u30C6\u30AD\u30B9\u30C8\u30C1\u30E3\u30F3\u30CD\u30EB" not in exported


def test_patch_yaml_keeps_omitted_sections_and_fields() -> None:
    current = parse_schema_dict(base_payload())
    uploaded = yaml.safe_dump(
        {"channels": [{"id": "20", "topic": "patched"}]},
        sort_keys=False,
    ).encode("utf-8")

    merged = parse_schema_patch_yaml(uploaded, current)

    assert len(merged.roles) == 1
    assert merged.roles[0].name == "Mod"
    assert len(merged.channels) == 1
    assert merged.channels[0].topic == "patched"
    assert merged.channels[0].name == "general"


def test_patch_yaml_can_prefer_name_matching_when_requested() -> None:
    current = parse_schema_dict(base_payload())
    uploaded = yaml.safe_dump(
        {
            "roles": [
                {
                    "id": "999",
                    "name": "Mod",
                    "permissions": ["manage_channels", "kick_members"],
                }
            ]
        },
        sort_keys=False,
    ).encode("utf-8")

    default_merged = parse_schema_patch_yaml(uploaded, current)
    assert len(default_merged.roles) == 2

    name_priority_merged = parse_schema_patch_yaml(
        uploaded,
        current,
        prefer_name_matching=True,
    )
    assert len(name_priority_merged.roles) == 1
    assert name_priority_merged.roles[0].permissions == [
        "manage_channels",
        "kick_members",
    ]


def test_patch_yaml_reports_multiple_duplicate_name_errors() -> None:
    current_payload = base_payload()
    current_payload["channels"] = [
        {"id": "20", "name": "general", "type": "text", "overwrites": []},
        {"id": "21", "name": "general", "type": "text", "overwrites": []},
    ]
    current = parse_schema_dict(current_payload)
    uploaded = yaml.safe_dump(
        {
            "channels": [
                {"name": "general", "topic": "a"},
                {"name": "general", "topic": "b"},
            ]
        },
        sort_keys=False,
    ).encode("utf-8")

    with pytest.raises(SchemaValidationError) as exc:
        parse_schema_patch_yaml(uploaded, current)

    message = str(exc.value)
    assert (
        "channels[0].name: name-only duplicate match in channels: 'general'" in message
    )
    assert (
        "channels[1].name: name-only duplicate match in channels: 'general'" in message
    )


def test_patch_yaml_can_continue_on_ambiguous_name_match_when_allowed() -> None:
    current_payload = base_payload()
    current_payload["channels"] = [
        {"id": "20", "name": "general", "type": "text", "overwrites": []},
        {"id": "21", "name": "general", "type": "voice", "overwrites": []},
    ]
    current = parse_schema_dict(current_payload)
    uploaded = yaml.safe_dump(
        {
            "channels": [
                {"name": "general", "topic": "patched"},
            ]
        },
        sort_keys=False,
    ).encode("utf-8")

    merged = parse_schema_patch_yaml(
        uploaded,
        current,
        allow_ambiguous_name_match=True,
        strict_relationship_validation=False,
    )

    assert len(merged.channels) == 2
    assert any(channel.topic == "patched" for channel in merged.channels)


def test_patch_yaml_can_continue_with_same_parent_type_name_duplicates() -> None:
    current_payload = base_payload()
    current_payload["categories"] = [
        {"id": "100", "name": "A", "position": 0, "overwrites": []}
    ]
    current_payload["channels"] = [
        {
            "id": "20",
            "name": "general",
            "type": "text",
            "parent_id": "100",
            "topic": "first",
            "overwrites": [],
        },
        {
            "id": "21",
            "name": "general",
            "type": "text",
            "parent_id": "100",
            "topic": "second",
            "overwrites": [],
        },
    ]
    current = parse_schema_dict(current_payload)
    uploaded = yaml.safe_dump(
        {
            "channels": [
                {
                    "name": "general",
                    "type": "text",
                    "parent_id": "100",
                    "topic": "patched",
                }
            ]
        },
        sort_keys=False,
    ).encode("utf-8")

    merged = parse_schema_patch_yaml(
        uploaded,
        current,
        allow_ambiguous_name_match=True,
        strict_relationship_validation=False,
    )

    assert len(merged.channels) == 2
    assert any(channel.topic == "patched" for channel in merged.channels)


def test_patch_yaml_name_priority_resolves_foreign_parent_id_by_category_name() -> None:
    current_payload = base_payload()
    current_payload["categories"] = [
        {"id": "100", "name": "テキストチャンネル", "position": 0, "overwrites": []}
    ]
    current_payload["channels"] = [
        {
            "id": "20",
            "name": "一般",
            "type": "text",
            "parent_id": "100",
            "topic": "old",
            "overwrites": [],
        }
    ]
    current = parse_schema_dict(current_payload)
    uploaded = yaml.safe_dump(
        {
            "categories": [
                {
                    "id": "900",
                    "name": "テキストチャンネル",
                }
            ],
            "channels": [
                {
                    "id": "901",
                    "name": "一般",
                    "type": "text",
                    "parent_id": "900",
                    "topic": "patched",
                }
            ],
        },
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")

    merged = parse_schema_patch_yaml(
        uploaded,
        current,
        prefer_name_matching=True,
        strict_relationship_validation=False,
    )

    assert len(merged.channels) == 1
    assert merged.channels[0].topic == "patched"


def test_patch_yaml_name_priority_normalizes_foreign_parent_id_on_apply_path() -> None:
    current_payload = base_payload()
    current_payload["categories"] = [
        {"id": "100", "name": "テキストチャンネル", "position": 0, "overwrites": []}
    ]
    current_payload["channels"] = [
        {
            "id": "20",
            "name": "一般",
            "type": "text",
            "parent_id": "100",
            "topic": "old",
            "overwrites": [],
        }
    ]
    current = parse_schema_dict(current_payload)
    uploaded = yaml.safe_dump(
        {
            "channels": [
                {
                    "id": "901",
                    "name": "一般",
                    "type": "text",
                    "parent_id": "900",
                    "topic": "patched",
                }
            ],
        },
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")

    merged = parse_schema_patch_yaml(
        uploaded,
        current,
        prefer_name_matching=True,
    )

    assert len(merged.channels) == 1
    assert merged.channels[0].topic == "patched"
    assert merged.channels[0].parent_id == "100"
