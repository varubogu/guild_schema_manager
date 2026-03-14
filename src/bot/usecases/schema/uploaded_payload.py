from __future__ import annotations

import json
from typing import cast

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal runtime
    yaml = None

from .export_ops import dump_mapping_yaml


def try_load_uploaded_mapping(uploaded: bytes | str) -> dict[str, object] | None:
    try:
        payload = load_uploaded_mapping(uploaded)
    except ValueError:
        return None
    populate_channel_parent_names_from_uploaded_payload(payload)
    return payload


def extract_uploaded_guild_id(uploaded: bytes | str) -> str | None:
    try:
        payload = load_uploaded_mapping(uploaded)
    except ValueError:
        return None

    guild_value = payload.get("guild")
    if not isinstance(guild_value, dict):
        return None
    guild_payload = cast(dict[str, object], guild_value)

    guild_id = guild_payload.get("id")
    if not isinstance(guild_id, str) or not guild_id:
        return None
    return guild_id


def overwrite_uploaded_guild_id(uploaded: bytes | str, guild_id: str) -> bytes:
    payload = load_uploaded_mapping(uploaded)
    guild_value = payload.get("guild")
    guild_payload: dict[str, object] = {}
    if isinstance(guild_value, dict):
        guild_payload = dict(cast(dict[str, object], guild_value))
    guild_payload["id"] = guild_id
    payload["guild"] = guild_payload
    return dump_mapping_yaml(payload).encode("utf-8")


def load_uploaded_mapping(uploaded: bytes | str) -> dict[str, object]:
    text = uploaded.decode("utf-8") if isinstance(uploaded, bytes) else uploaded
    if yaml is not None:
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML: {exc}") from exc
    else:
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid YAML/JSON payload: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError("Top-level YAML must be a mapping")
    return cast(dict[str, object], loaded)


def category_name_by_id_from_payload(payload: dict[str, object]) -> dict[str, str]:
    categories_value = payload.get("categories")
    if not isinstance(categories_value, list):
        return {}
    mapped: dict[str, str] = {}
    for raw_category in cast(list[object], categories_value):
        if not isinstance(raw_category, dict):
            continue
        category = cast(dict[str, object], raw_category)
        category_id = category.get("id")
        category_name = category.get("name")
        if (
            isinstance(category_id, str)
            and category_id
            and isinstance(category_name, str)
            and category_name
        ):
            mapped[category_id] = category_name
    return mapped


def populate_channel_parent_names_from_uploaded_payload(
    payload: dict[str, object],
) -> None:
    category_name_by_id = category_name_by_id_from_payload(payload)
    if not category_name_by_id:
        return
    channels_value = payload.get("channels")
    if not isinstance(channels_value, list):
        return
    for raw_channel in cast(list[object], channels_value):
        if not isinstance(raw_channel, dict):
            continue
        channel = cast(dict[str, object], raw_channel)
        parent_name = channel.get("parent_name")
        if isinstance(parent_name, str) and parent_name:
            continue
        parent_id = channel.get("parent_id")
        if not isinstance(parent_id, str) or not parent_id:
            continue
        resolved = category_name_by_id.get(parent_id)
        if resolved is None:
            continue
        channel["parent_name"] = resolved


__all__ = [
    "category_name_by_id_from_payload",
    "extract_uploaded_guild_id",
    "load_uploaded_mapping",
    "overwrite_uploaded_guild_id",
    "populate_channel_parent_names_from_uploaded_payload",
    "try_load_uploaded_mapping",
]
