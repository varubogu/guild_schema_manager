from __future__ import annotations

from typing import Any

import pytest

from bot.schema import SchemaValidationError, parse_schema_dict, schema_to_yaml


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


def test_schema_to_yaml_preserves_japanese_characters() -> None:
    payload = base_payload()
    payload["guild"]["name"] = "日本語サーバー"
    payload["channels"][0]["name"] = "テキストチャンネル"
    schema = parse_schema_dict(payload)

    exported = schema_to_yaml(schema)

    assert "テキストチャンネル" in exported
    assert r"\u30C6\u30AD\u30B9\u30C8\u30C1\u30E3\u30F3\u30CD\u30EB" not in exported
