from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TypeGuard, cast

from bot.usecases.schema_model.models import (
    CategorySchema,
    ChannelType,
    ChannelSchema,
    GuildInfo,
    GuildSchema,
    OverwriteTarget,
    PermissionOverwrite,
    RoleSchema,
)
from bot.usecases.schema_model.parser import parse_schema_dict, schema_to_dict


def clone_snapshot(snapshot: GuildSchema) -> GuildSchema:
    return parse_schema_dict(schema_to_dict(snapshot))


def build_snapshot_from_mapping(payload: dict[str, object]) -> GuildSchema:
    return parse_schema_dict(payload)


def build_snapshot_from_guild(guild: object) -> GuildSchema:
    roles = [_role_to_schema(role) for role in getattr(guild, "roles", [])]
    categories = [
        _category_to_schema(category) for category in getattr(guild, "categories", [])
    ]

    channels: list[ChannelSchema] = []
    for channel in getattr(guild, "channels", []):
        if channel.__class__.__name__.lower().startswith("category"):
            continue
        channels.append(_channel_to_schema(channel))

    return GuildSchema(
        version=1,
        guild=GuildInfo(id=str(getattr(guild, "id")), name=str(getattr(guild, "name"))),
        roles=roles,
        categories=categories,
        channels=channels,
    )


def _role_to_schema(role: object) -> RoleSchema:
    permissions: list[str] = []
    perms_obj = getattr(role, "permissions", None)
    if perms_obj is not None:
        permissions = [
            name for name, enabled in _iter_name_enabled_pairs(perms_obj) if enabled
        ]

    color_value = getattr(getattr(role, "color", None), "value", 0)
    return RoleSchema(
        id=str(getattr(role, "id")),
        name=str(getattr(role, "name")),
        bot_managed=_is_bot_managed_role(role),
        color=int(color_value),
        hoist=bool(getattr(role, "hoist", False)),
        mentionable=bool(getattr(role, "mentionable", False)),
        permissions=sorted(permissions),
        position=int(getattr(role, "position", 0)),
    )


def _category_to_schema(category: object) -> CategorySchema:
    return CategorySchema(
        id=str(getattr(category, "id")),
        name=str(getattr(category, "name")),
        position=int(getattr(category, "position", 0)),
        overwrites=_extract_overwrites(getattr(category, "overwrites", None)),
    )


def _channel_to_schema(channel: object) -> ChannelSchema:
    type_name = str(getattr(getattr(channel, "type", None), "name", "text"))
    parent = getattr(channel, "category", None)
    parent_id = str(getattr(parent, "id")) if parent is not None else None
    parent_name = str(getattr(parent, "name")) if parent is not None else None
    return ChannelSchema(
        id=str(getattr(channel, "id")),
        name=str(getattr(channel, "name")),
        type=_normalize_channel_type(type_name),
        parent_id=parent_id,
        parent_name=parent_name,
        position=int(getattr(channel, "position", 0)),
        topic=getattr(channel, "topic", None),
        nsfw=bool(getattr(channel, "nsfw", False)),
        slowmode_delay=int(getattr(channel, "slowmode_delay", 0)),
        overwrites=_extract_overwrites(getattr(channel, "overwrites", None)),
    )


def _extract_overwrites(raw: object) -> list[PermissionOverwrite]:
    if raw is None:
        return []

    pairs: Iterable[tuple[object, object]]
    if isinstance(raw, Mapping):
        pairs = cast(Mapping[object, object], raw).items()
    elif isinstance(raw, list):
        raw_list = cast(list[object], raw)
        normalized: list[tuple[object, object]] = []
        for item in raw_list:
            if _is_object_pair(item):
                normalized.append(item)
        pairs = normalized
    else:
        return []

    result: list[PermissionOverwrite] = []
    for target, overwrite in pairs:
        allow: list[str] = []
        deny: list[str] = []
        if hasattr(overwrite, "pair"):
            pair_method = getattr(overwrite, "pair")
            if callable(pair_method):
                pair_result = pair_method()
                if _is_object_pair(pair_result):
                    allow_obj, deny_obj = pair_result
                    allow = [
                        name
                        for name, enabled in _iter_name_enabled_pairs(allow_obj)
                        if enabled
                    ]
                    deny = [
                        name
                        for name, enabled in _iter_name_enabled_pairs(deny_obj)
                        if enabled
                    ]
        target_type = (
            "role" if target.__class__.__name__.lower().endswith("role") else "member"
        )
        result.append(
            PermissionOverwrite(
                target=OverwriteTarget(type=target_type, id=str(getattr(target, "id"))),
                allow=sorted(allow),
                deny=sorted(deny),
            )
        )
    return result


def _normalize_channel_type(type_name: str) -> ChannelType:
    mapping: dict[str, ChannelType] = {
        "text": "text",
        "voice": "voice",
        "news": "news",
        "announcement": "news",
        "stage_voice": "stage_voice",
        "stage": "stage_voice",
        "forum": "forum",
        "media": "media",
    }
    return mapping.get(type_name, "text")


def _iter_name_enabled_pairs(raw: object) -> list[tuple[str, bool]]:
    if isinstance(raw, str) or not isinstance(raw, Iterable):
        return []
    iterable = cast(Iterable[object], raw)

    result: list[tuple[str, bool]] = []
    for item in iterable:
        if not _is_object_pair(item):
            continue
        name, enabled = item
        if isinstance(name, str) and isinstance(enabled, bool):
            result.append((name, enabled))
    return result


def _is_object_pair(value: object) -> TypeGuard[tuple[object, object]]:
    if not isinstance(value, tuple):
        return False
    return len(cast(tuple[object, ...], value)) == 2


def _is_bot_managed_role(role: object) -> bool:
    is_bot_managed = getattr(role, "is_bot_managed", None)
    if callable(is_bot_managed):
        return bool(is_bot_managed())

    tags = getattr(role, "tags", None)
    if tags is None:
        return False
    return getattr(tags, "bot_id", None) is not None
