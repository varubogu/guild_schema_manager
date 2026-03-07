from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bot.schema.models import (
    CategorySchema,
    ChannelSchema,
    GuildInfo,
    GuildSchema,
    OverwriteTarget,
    PermissionOverwrite,
    RoleSchema,
)
from bot.schema.parser import parse_schema_dict, schema_to_dict


def clone_snapshot(snapshot: GuildSchema) -> GuildSchema:
    return parse_schema_dict(schema_to_dict(snapshot))


def build_snapshot_from_mapping(payload: dict[str, Any]) -> GuildSchema:
    return parse_schema_dict(payload)


def build_snapshot_from_guild(guild: Any) -> GuildSchema:
    roles = [_role_to_schema(role) for role in getattr(guild, "roles", [])]
    categories = [_category_to_schema(category) for category in getattr(guild, "categories", [])]

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


def _role_to_schema(role: Any) -> RoleSchema:
    permissions = []
    perms_obj = getattr(role, "permissions", None)
    if perms_obj is not None and hasattr(perms_obj, "__iter__"):
        permissions = [name for name, enabled in perms_obj if enabled]

    color_value = getattr(getattr(role, "color", None), "value", 0)
    return RoleSchema(
        id=str(getattr(role, "id")),
        name=str(getattr(role, "name")),
        color=int(color_value),
        hoist=bool(getattr(role, "hoist", False)),
        mentionable=bool(getattr(role, "mentionable", False)),
        permissions=sorted(permissions),
        position=int(getattr(role, "position", 0)),
    )


def _category_to_schema(category: Any) -> CategorySchema:
    return CategorySchema(
        id=str(getattr(category, "id")),
        name=str(getattr(category, "name")),
        position=int(getattr(category, "position", 0)),
        overwrites=_extract_overwrites(getattr(category, "overwrites", None)),
    )


def _channel_to_schema(channel: Any) -> ChannelSchema:
    type_name = str(getattr(getattr(channel, "type", None), "name", "text"))
    parent = getattr(channel, "category", None)
    parent_id = str(getattr(parent, "id")) if parent is not None else None
    return ChannelSchema(
        id=str(getattr(channel, "id")),
        name=str(getattr(channel, "name")),
        type=_normalize_channel_type(type_name),
        parent_id=parent_id,
        position=int(getattr(channel, "position", 0)),
        topic=getattr(channel, "topic", None),
        nsfw=bool(getattr(channel, "nsfw", False)),
        slowmode_delay=int(getattr(channel, "slowmode_delay", 0)),
        overwrites=_extract_overwrites(getattr(channel, "overwrites", None)),
    )


def _extract_overwrites(raw: Any) -> list[PermissionOverwrite]:
    if raw is None:
        return []

    pairs: Iterable[tuple[Any, Any]]
    if hasattr(raw, "items"):
        pairs = raw.items()
    elif isinstance(raw, list):
        pairs = raw
    else:
        return []

    result: list[PermissionOverwrite] = []
    for target, overwrite in pairs:
        allow: list[str] = []
        deny: list[str] = []
        if hasattr(overwrite, "pair"):
            allow_obj, deny_obj = overwrite.pair()
            allow = [name for name, enabled in allow_obj if enabled]
            deny = [name for name, enabled in deny_obj if enabled]
        target_type = "role" if target.__class__.__name__.lower().endswith("role") else "member"
        result.append(
            PermissionOverwrite(
                target=OverwriteTarget(type=target_type, id=str(getattr(target, "id"))),
                allow=sorted(allow),
                deny=sorted(deny),
            )
        )
    return result


def _normalize_channel_type(type_name: str) -> str:
    mapping = {
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
