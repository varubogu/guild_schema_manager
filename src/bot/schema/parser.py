from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal runtime
    yaml = None

from .errors import SchemaValidationError
from .models import (
    CategorySchema,
    ChannelSchema,
    GuildInfo,
    GuildSchema,
    OverwriteTarget,
    PermissionOverwrite,
    RoleSchema,
)

_ALLOWED_TOP_LEVEL_KEYS = {"version", "guild", "roles", "categories", "channels"}
_ALLOWED_GUILD_KEYS = {"id", "name"}
_ALLOWED_ROLE_KEYS = {
    "id",
    "name",
    "color",
    "hoist",
    "mentionable",
    "permissions",
    "position",
}
_ALLOWED_CATEGORY_KEYS = {"id", "name", "position", "overwrites"}
_ALLOWED_CHANNEL_KEYS = {
    "id",
    "name",
    "type",
    "parent_id",
    "parent_name",
    "position",
    "topic",
    "nsfw",
    "slowmode_delay",
    "overwrites",
}
_ALLOWED_OVERWRITE_KEYS = {"target", "allow", "deny"}
_ALLOWED_TARGET_KEYS = {"type", "id"}
_ALLOWED_TARGET_TYPES = {"role", "member"}
_SUPPORTED_CHANNEL_TYPES = {"text", "voice", "news", "stage_voice", "forum", "media"}


def parse_schema_yaml(raw: bytes | str) -> GuildSchema:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    if yaml is not None:
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SchemaValidationError(f"Invalid YAML: {exc}") from exc
    else:
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SchemaValidationError(f"Invalid YAML/JSON payload: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SchemaValidationError("Top-level YAML must be a mapping")
    return parse_schema_dict(loaded)


def parse_schema_dict(payload: dict[str, Any]) -> GuildSchema:
    _ensure_known_keys(payload, _ALLOWED_TOP_LEVEL_KEYS, "")
    _require_keys(payload, {"version", "guild", "roles", "categories", "channels"}, "")

    guild = _parse_guild(payload["guild"])
    roles = _parse_roles(payload.get("roles", []))
    categories = _parse_categories(payload.get("categories", []))
    channels = _parse_channels(payload.get("channels", []))

    _validate_duplicate_ids(roles, "roles")
    _validate_duplicate_ids(categories, "categories")
    _validate_duplicate_ids(channels, "channels")
    _validate_parent_references(channels, categories)
    _validate_overwrite_targets(categories, channels, roles)

    version = payload["version"]
    if not isinstance(version, int):
        raise SchemaValidationError("version must be integer", "version")

    return GuildSchema(
        version=version,
        guild=guild,
        roles=roles,
        categories=categories,
        channels=channels,
    )


def schema_to_dict(schema: GuildSchema) -> dict[str, Any]:
    return asdict(schema)


def schema_to_yaml(schema: GuildSchema) -> str:
    if yaml is not None:
        return yaml.safe_dump(
            schema_to_dict(schema), sort_keys=False, allow_unicode=True
        )
    return json.dumps(schema_to_dict(schema), indent=2, ensure_ascii=False)


def _parse_guild(payload: Any) -> GuildInfo:
    if not isinstance(payload, dict):
        raise SchemaValidationError("guild must be an object", "guild")
    _ensure_known_keys(payload, _ALLOWED_GUILD_KEYS, "guild")
    _require_keys(payload, {"id", "name"}, "guild")
    if not isinstance(payload["id"], str) or not payload["id"]:
        raise SchemaValidationError("id must be non-empty string", "guild.id")
    if not isinstance(payload["name"], str) or not payload["name"]:
        raise SchemaValidationError("name must be non-empty string", "guild.name")
    return GuildInfo(id=payload["id"], name=payload["name"])


def _parse_roles(payload: Any) -> list[RoleSchema]:
    if not isinstance(payload, list):
        raise SchemaValidationError("roles must be an array", "roles")
    items: list[RoleSchema] = []
    for idx, item in enumerate(payload):
        path = f"roles[{idx}]"
        if not isinstance(item, dict):
            raise SchemaValidationError("role must be object", path)
        _ensure_known_keys(item, _ALLOWED_ROLE_KEYS, path)
        _require_keys(item, {"name"}, path)
        role = RoleSchema(
            id=_opt_str(item.get("id"), f"{path}.id"),
            name=_required_str(item.get("name"), f"{path}.name"),
            color=_opt_int(item.get("color", 0), f"{path}.color"),
            hoist=_opt_bool(item.get("hoist", False), f"{path}.hoist"),
            mentionable=_opt_bool(
                item.get("mentionable", False), f"{path}.mentionable"
            ),
            permissions=_list_of_str(
                item.get("permissions", []), f"{path}.permissions"
            ),
            position=_opt_int(item.get("position", 0), f"{path}.position"),
        )
        items.append(role)
    return items


def _parse_categories(payload: Any) -> list[CategorySchema]:
    if not isinstance(payload, list):
        raise SchemaValidationError("categories must be an array", "categories")
    items: list[CategorySchema] = []
    for idx, item in enumerate(payload):
        path = f"categories[{idx}]"
        if not isinstance(item, dict):
            raise SchemaValidationError("category must be object", path)
        _ensure_known_keys(item, _ALLOWED_CATEGORY_KEYS, path)
        _require_keys(item, {"name"}, path)
        items.append(
            CategorySchema(
                id=_opt_str(item.get("id"), f"{path}.id"),
                name=_required_str(item.get("name"), f"{path}.name"),
                position=_opt_int(item.get("position", 0), f"{path}.position"),
                overwrites=_parse_overwrites(
                    item.get("overwrites", []), f"{path}.overwrites"
                ),
            )
        )
    return items


def _parse_channels(payload: Any) -> list[ChannelSchema]:
    if not isinstance(payload, list):
        raise SchemaValidationError("channels must be an array", "channels")
    items: list[ChannelSchema] = []
    for idx, item in enumerate(payload):
        path = f"channels[{idx}]"
        if not isinstance(item, dict):
            raise SchemaValidationError("channel must be object", path)
        _ensure_known_keys(item, _ALLOWED_CHANNEL_KEYS, path)
        _require_keys(item, {"name", "type"}, path)
        channel_type = _required_str(item.get("type"), f"{path}.type")
        if channel_type not in _SUPPORTED_CHANNEL_TYPES:
            raise SchemaValidationError(
                f"unsupported channel type '{channel_type}'",
                f"{path}.type",
            )
        items.append(
            ChannelSchema(
                id=_opt_str(item.get("id"), f"{path}.id"),
                name=_required_str(item.get("name"), f"{path}.name"),
                type=channel_type,  # type: ignore[arg-type]
                parent_id=_opt_str(item.get("parent_id"), f"{path}.parent_id"),
                parent_name=_opt_str(item.get("parent_name"), f"{path}.parent_name"),
                position=_opt_int(item.get("position", 0), f"{path}.position"),
                topic=_opt_str(item.get("topic"), f"{path}.topic"),
                nsfw=_opt_bool(item.get("nsfw", False), f"{path}.nsfw"),
                slowmode_delay=_opt_int(
                    item.get("slowmode_delay", 0), f"{path}.slowmode_delay"
                ),
                overwrites=_parse_overwrites(
                    item.get("overwrites", []), f"{path}.overwrites"
                ),
            )
        )
    return items


def _parse_overwrites(payload: Any, path: str) -> list[PermissionOverwrite]:
    if not isinstance(payload, list):
        raise SchemaValidationError("overwrites must be an array", path)
    items: list[PermissionOverwrite] = []
    for idx, item in enumerate(payload):
        ow_path = f"{path}[{idx}]"
        if not isinstance(item, dict):
            raise SchemaValidationError("overwrite must be object", ow_path)
        _ensure_known_keys(item, _ALLOWED_OVERWRITE_KEYS, ow_path)
        _require_keys(item, {"target"}, ow_path)

        target_payload = item["target"]
        if not isinstance(target_payload, dict):
            raise SchemaValidationError("target must be object", f"{ow_path}.target")
        _ensure_known_keys(target_payload, _ALLOWED_TARGET_KEYS, f"{ow_path}.target")
        _require_keys(target_payload, {"type", "id"}, f"{ow_path}.target")

        target_type = _required_str(
            target_payload.get("type"), f"{ow_path}.target.type"
        )
        if target_type not in _ALLOWED_TARGET_TYPES:
            raise SchemaValidationError(
                f"unsupported overwrite target type '{target_type}'",
                f"{ow_path}.target.type",
            )

        target_id = _required_str(target_payload.get("id"), f"{ow_path}.target.id")
        items.append(
            PermissionOverwrite(
                target=OverwriteTarget(type=target_type, id=target_id),  # type: ignore[arg-type]
                allow=_list_of_str(item.get("allow", []), f"{ow_path}.allow"),
                deny=_list_of_str(item.get("deny", []), f"{ow_path}.deny"),
            )
        )
    return items


def _validate_duplicate_ids(items: list[Any], section: str) -> None:
    ids = [item.id for item in items if getattr(item, "id", None)]
    dupes = [value for value, count in Counter(ids).items() if count > 1]
    if dupes:
        raise SchemaValidationError(
            f"duplicate explicit IDs found: {', '.join(dupes)}",
            section,
        )


def _validate_parent_references(
    channels: list[ChannelSchema], categories: list[CategorySchema]
) -> None:
    category_ids = {category.id for category in categories if category.id}
    category_names = {category.name for category in categories}
    for idx, channel in enumerate(channels):
        if (
            channel.parent_id
            and channel.parent_name
            and channel.parent_name not in category_names
        ):
            raise SchemaValidationError(
                "parent_id and parent_name conflict (parent_name not found)",
                f"channels[{idx}]",
            )
        if channel.parent_id and channel.parent_id not in category_ids:
            raise SchemaValidationError(
                "parent_id does not reference any category id",
                f"channels[{idx}].parent_id",
            )


def _validate_overwrite_targets(
    categories: list[CategorySchema],
    channels: list[ChannelSchema],
    roles: list[RoleSchema],
) -> None:
    role_ids = {role.id for role in roles if role.id}
    containers = [*categories, *channels]
    for container_idx, container in enumerate(containers):
        for ow_idx, overwrite in enumerate(container.overwrites):
            if overwrite.target.type == "role" and overwrite.target.id not in role_ids:
                prefix = "categories" if container_idx < len(categories) else "channels"
                idx = (
                    container_idx
                    if prefix == "categories"
                    else container_idx - len(categories)
                )
                raise SchemaValidationError(
                    f"overwrite role target id '{overwrite.target.id}' not found in roles",
                    f"{prefix}[{idx}].overwrites[{ow_idx}].target.id",
                )


def _ensure_known_keys(payload: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        location = path or "<root>"
        raise SchemaValidationError(
            f"unknown keys: {', '.join(unknown)}",
            location,
        )


def _require_keys(payload: dict[str, Any], required: set[str], path: str) -> None:
    missing = sorted(key for key in required if key not in payload)
    if missing:
        location = path or "<root>"
        raise SchemaValidationError(
            f"missing required keys: {', '.join(missing)}",
            location,
        )


def _required_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise SchemaValidationError("must be non-empty string", path)
    return value


def _opt_str(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaValidationError("must be string", path)
    return value


def _opt_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaValidationError("must be integer", path)
    return value


def _opt_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise SchemaValidationError("must be boolean", path)
    return value


def _list_of_str(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise SchemaValidationError("must be array", path)
    result: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise SchemaValidationError("array values must be string", f"{path}[{idx}]")
        result.append(item)
    return result
