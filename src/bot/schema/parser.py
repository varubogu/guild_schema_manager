from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from typing import Any, cast

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal runtime
    yaml = None

from .errors import SchemaValidationError
from .models import (
    CategorySchema,
    ChannelType,
    ChannelSchema,
    GuildInfo,
    GuildSchema,
    OverwriteTargetType,
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


def parse_schema_yaml(
    raw: bytes | str,
    *,
    strict_relationship_validation: bool = True,
) -> GuildSchema:
    payload = _load_yaml_mapping(raw)
    return parse_schema_dict(
        payload,
        strict_relationship_validation=strict_relationship_validation,
    )


def parse_schema_patch_yaml(
    raw: bytes | str,
    current: GuildSchema,
    *,
    prefer_name_matching: bool = False,
    allow_ambiguous_name_match: bool = False,
    strict_relationship_validation: bool = True,
) -> GuildSchema:
    patch_payload = _load_yaml_mapping(raw)
    merged_payload = _merge_schema_patch(
        schema_to_dict(current),
        patch_payload,
        prefer_name_matching=prefer_name_matching,
        allow_ambiguous_name_match=allow_ambiguous_name_match,
    )
    return parse_schema_dict(
        merged_payload,
        strict_relationship_validation=strict_relationship_validation,
    )


def _load_yaml_mapping(raw: bytes | str) -> dict[str, object]:
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
    return cast(dict[str, object], loaded)


def _merge_schema_patch(
    current_payload: dict[str, object],
    patch_payload: dict[str, object],
    *,
    prefer_name_matching: bool,
    allow_ambiguous_name_match: bool,
) -> dict[str, object]:
    merged = dict(current_payload)
    for key, value in patch_payload.items():
        if key == "guild":
            merged["guild"] = _merge_guild_payload(current_payload.get("guild"), value)
            continue
        if key in {"roles", "categories", "channels"}:
            merged[key] = _merge_entity_payload(
                current_payload.get(key),
                value,
                section=key,
                prefer_name_matching=prefer_name_matching,
                allow_ambiguous_name_match=allow_ambiguous_name_match,
            )
            continue
        merged[key] = value
    return merged


def _merge_guild_payload(
    current_value: object,
    patch_value: object,
) -> object:
    if not isinstance(current_value, dict) or not isinstance(patch_value, dict):
        return patch_value

    merged = dict(cast(dict[str, object], current_value))
    merged.update(cast(dict[str, object], patch_value))
    return merged


def _merge_entity_payload(
    current_value: object,
    patch_value: object,
    *,
    section: str,
    prefer_name_matching: bool,
    allow_ambiguous_name_match: bool,
) -> object:
    if not isinstance(current_value, list) or not isinstance(patch_value, list):
        return patch_value

    current_items = cast(list[object], current_value)
    merged_items = list(current_items)
    matched_indices: set[int] = set()
    validation_errors: list[SchemaValidationError] = []

    for patch_index, patch_item in enumerate(cast(list[object], patch_value)):
        if not isinstance(patch_item, dict):
            merged_items.append(patch_item)
            continue

        patch_item_dict = cast(dict[str, object], patch_item)
        try:
            matched_index = _find_match_index(
                current_items=current_items,
                patch_item=patch_item_dict,
                section=section,
                patch_index=patch_index,
                matched_indices=matched_indices,
                prefer_name_matching=prefer_name_matching,
                allow_ambiguous_name_match=allow_ambiguous_name_match,
            )
        except SchemaValidationError as exc:
            validation_errors.append(exc)
            continue
        if matched_index is None:
            merged_items.append(patch_item_dict)
            continue

        current_item = current_items[matched_index]
        if not isinstance(current_item, dict):
            merged_items.append(patch_item_dict)
            continue

        merged_item = dict(cast(dict[str, object], current_item))
        merged_item.update(patch_item_dict)
        merged_items[matched_index] = merged_item
        matched_indices.add(matched_index)

    if validation_errors:
        raise _compose_validation_error(validation_errors)

    return merged_items


def _find_match_index(
    *,
    current_items: list[object],
    patch_item: dict[str, object],
    section: str,
    patch_index: int,
    matched_indices: set[int],
    prefer_name_matching: bool,
    allow_ambiguous_name_match: bool,
) -> int | None:
    if prefer_name_matching:
        name_match = _find_name_match_index(
            current_items=current_items,
            patch_item=patch_item,
            section=section,
            patch_index=patch_index,
            matched_indices=matched_indices,
            prefer_name_matching=prefer_name_matching,
            allow_ambiguous_name_match=allow_ambiguous_name_match,
        )
        if name_match is not None:
            return name_match
        return _find_id_match_index(
            current_items=current_items,
            patch_item=patch_item,
            section=section,
            patch_index=patch_index,
            matched_indices=matched_indices,
        )

    id_match = _find_id_match_index(
        current_items=current_items,
        patch_item=patch_item,
        section=section,
        patch_index=patch_index,
        matched_indices=matched_indices,
    )
    if _id_only_match_required(patch_item):
        return id_match
    if id_match is not None:
        return id_match
    return _find_name_match_index(
        current_items=current_items,
        patch_item=patch_item,
        section=section,
        patch_index=patch_index,
        matched_indices=matched_indices,
        prefer_name_matching=prefer_name_matching,
        allow_ambiguous_name_match=allow_ambiguous_name_match,
    )


def _find_id_match_index(
    *,
    current_items: list[object],
    patch_item: dict[str, object],
    section: str,
    patch_index: int,
    matched_indices: set[int],
) -> int | None:
    patch_id = patch_item.get("id")
    if isinstance(patch_id, str) and patch_id:
        for idx, current_item in enumerate(current_items):
            if not isinstance(current_item, dict):
                continue
            if cast(dict[str, object], current_item).get("id") != patch_id:
                continue
            if idx in matched_indices:
                raise SchemaValidationError(
                    f"duplicate patch entries for id '{patch_id}'",
                    f"{section}[{patch_index}].id",
                )
            return idx
        return None

    if (
        "id" in patch_item
        and patch_id not in (None, "")
        and not isinstance(patch_id, str)
    ):
        return None
    return None


def _find_name_match_index(
    *,
    current_items: list[object],
    patch_item: dict[str, object],
    section: str,
    patch_index: int,
    matched_indices: set[int],
    prefer_name_matching: bool,
    allow_ambiguous_name_match: bool,
) -> int | None:
    patch_name = patch_item.get("name")
    if not isinstance(patch_name, str) or not patch_name:
        return None

    all_candidates: list[int] = []
    patch_channel_type: str | None = None
    patch_parent_scope: str | None = None
    if section == "channels":
        patch_type = patch_item.get("type")
        if isinstance(patch_type, str) and patch_type:
            patch_channel_type = patch_type
        patch_parent_scope = _channel_parent_scope_from_mapping(
            patch_item,
            prefer_name_matching=prefer_name_matching,
        )

    for idx, current_item in enumerate(current_items):
        if not isinstance(current_item, dict):
            continue
        current_item_dict = cast(dict[str, object], current_item)
        if current_item_dict.get("name") != patch_name:
            continue
        if (
            patch_channel_type is not None
            and current_item_dict.get("type") != patch_channel_type
        ):
            continue
        if section == "channels" and patch_parent_scope is not None:
            current_parent_scope = _channel_parent_scope_from_mapping(
                current_item_dict,
                prefer_name_matching=prefer_name_matching,
            )
            if current_parent_scope != patch_parent_scope:
                continue
        all_candidates.append(idx)

    if len(all_candidates) > 1:
        if allow_ambiguous_name_match:
            for candidate in all_candidates:
                if candidate not in matched_indices:
                    return candidate
            return None
        raise SchemaValidationError(
            f"name-only duplicate match in {section}: '{patch_name}'",
            f"{section}[{patch_index}].name",
        )

    if not all_candidates:
        return None

    matched = all_candidates[0]
    if matched in matched_indices:
        if allow_ambiguous_name_match:
            for candidate in all_candidates:
                if candidate not in matched_indices:
                    return candidate
            return None
        raise SchemaValidationError(
            f"duplicate patch entries for name '{patch_name}'",
            f"{section}[{patch_index}].name",
        )
    return matched


def _id_only_match_required(patch_item: dict[str, object]) -> bool:
    patch_id = patch_item.get("id")
    if isinstance(patch_id, str) and patch_id:
        return True
    return (
        "id" in patch_item
        and patch_id not in (None, "")
        and not isinstance(patch_id, str)
    )


def _channel_parent_scope_from_mapping(
    payload: dict[str, object],
    *,
    prefer_name_matching: bool,
) -> str | None:
    first = "parent_name" if prefer_name_matching else "parent_id"
    second = "parent_id" if prefer_name_matching else "parent_name"
    first_value = payload.get(first)
    if isinstance(first_value, str) and first_value:
        return first_value
    second_value = payload.get(second)
    if isinstance(second_value, str) and second_value:
        return second_value
    return None


def _compose_validation_error(
    errors: list[SchemaValidationError],
) -> SchemaValidationError:
    if len(errors) == 1:
        return errors[0]
    details = "\n".join(f"- {error}" for error in errors)
    return SchemaValidationError(f"multiple validation errors:\n{details}")


def parse_schema_dict(
    payload: dict[str, object],
    *,
    strict_relationship_validation: bool = True,
) -> GuildSchema:
    _ensure_known_keys(payload, _ALLOWED_TOP_LEVEL_KEYS, "")
    _require_keys(payload, {"version", "guild", "roles", "categories", "channels"}, "")

    guild = _parse_guild(payload["guild"])
    roles = _parse_roles(payload.get("roles", []))
    categories = _parse_categories(payload.get("categories", []))
    channels = _parse_channels(payload.get("channels", []))

    if strict_relationship_validation:
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


def schema_to_dict(schema: GuildSchema) -> dict[str, object]:
    return cast(dict[str, object], asdict(schema))


def schema_to_yaml(schema: GuildSchema) -> str:
    if yaml is not None:
        return yaml.safe_dump(
            schema_to_dict(schema), sort_keys=False, allow_unicode=True
        )
    return json.dumps(schema_to_dict(schema), indent=2, ensure_ascii=False)


def _parse_guild(payload: object) -> GuildInfo:
    guild_payload = _as_dict(payload, "guild must be an object", "guild")
    _ensure_known_keys(guild_payload, _ALLOWED_GUILD_KEYS, "guild")
    _require_keys(guild_payload, {"id", "name"}, "guild")
    guild_id = guild_payload["id"]
    guild_name = guild_payload["name"]
    if not isinstance(guild_id, str) or not guild_id:
        raise SchemaValidationError("id must be non-empty string", "guild.id")
    if not isinstance(guild_name, str) or not guild_name:
        raise SchemaValidationError("name must be non-empty string", "guild.name")
    return GuildInfo(id=guild_id, name=guild_name)


def _parse_roles(payload: object) -> list[RoleSchema]:
    role_items = _as_list(payload, "roles must be an array", "roles")
    items: list[RoleSchema] = []
    for idx, item in enumerate(role_items):
        path = f"roles[{idx}]"
        role_payload = _as_dict(item, "role must be object", path)
        _ensure_known_keys(role_payload, _ALLOWED_ROLE_KEYS, path)
        _require_keys(role_payload, {"name"}, path)
        role = RoleSchema(
            id=_opt_str(role_payload.get("id"), f"{path}.id"),
            name=_required_str(role_payload.get("name"), f"{path}.name"),
            color=_opt_int(role_payload.get("color", 0), f"{path}.color"),
            hoist=_opt_bool(role_payload.get("hoist", False), f"{path}.hoist"),
            mentionable=_opt_bool(
                role_payload.get("mentionable", False), f"{path}.mentionable"
            ),
            permissions=_list_of_str(
                role_payload.get("permissions", []), f"{path}.permissions"
            ),
            position=_opt_int(role_payload.get("position", 0), f"{path}.position"),
        )
        items.append(role)
    return items


def _parse_categories(payload: object) -> list[CategorySchema]:
    category_items = _as_list(payload, "categories must be an array", "categories")
    items: list[CategorySchema] = []
    for idx, item in enumerate(category_items):
        path = f"categories[{idx}]"
        category_payload = _as_dict(item, "category must be object", path)
        _ensure_known_keys(category_payload, _ALLOWED_CATEGORY_KEYS, path)
        _require_keys(category_payload, {"name"}, path)
        items.append(
            CategorySchema(
                id=_opt_str(category_payload.get("id"), f"{path}.id"),
                name=_required_str(category_payload.get("name"), f"{path}.name"),
                position=_opt_int(
                    category_payload.get("position", 0), f"{path}.position"
                ),
                overwrites=_parse_overwrites(
                    category_payload.get("overwrites", []), f"{path}.overwrites"
                ),
            )
        )
    return items


def _parse_channels(payload: object) -> list[ChannelSchema]:
    channel_items = _as_list(payload, "channels must be an array", "channels")
    items: list[ChannelSchema] = []
    for idx, item in enumerate(channel_items):
        path = f"channels[{idx}]"
        channel_payload = _as_dict(item, "channel must be object", path)
        _ensure_known_keys(channel_payload, _ALLOWED_CHANNEL_KEYS, path)
        _require_keys(channel_payload, {"name", "type"}, path)
        channel_type = _required_str(channel_payload.get("type"), f"{path}.type")
        if channel_type not in _SUPPORTED_CHANNEL_TYPES:
            raise SchemaValidationError(
                f"unsupported channel type '{channel_type}'",
                f"{path}.type",
            )
        typed_channel_type = cast(ChannelType, channel_type)
        items.append(
            ChannelSchema(
                id=_opt_str(channel_payload.get("id"), f"{path}.id"),
                name=_required_str(channel_payload.get("name"), f"{path}.name"),
                type=typed_channel_type,
                parent_id=_opt_str(
                    channel_payload.get("parent_id"), f"{path}.parent_id"
                ),
                parent_name=_opt_str(
                    channel_payload.get("parent_name"), f"{path}.parent_name"
                ),
                position=_opt_int(
                    channel_payload.get("position", 0), f"{path}.position"
                ),
                topic=_opt_str(channel_payload.get("topic"), f"{path}.topic"),
                nsfw=_opt_bool(channel_payload.get("nsfw", False), f"{path}.nsfw"),
                slowmode_delay=_opt_int(
                    channel_payload.get("slowmode_delay", 0),
                    f"{path}.slowmode_delay",
                ),
                overwrites=_parse_overwrites(
                    channel_payload.get("overwrites", []), f"{path}.overwrites"
                ),
            )
        )
    return items


def _parse_overwrites(payload: object, path: str) -> list[PermissionOverwrite]:
    overwrite_items = _as_list(payload, "overwrites must be an array", path)
    items: list[PermissionOverwrite] = []
    for idx, item in enumerate(overwrite_items):
        ow_path = f"{path}[{idx}]"
        overwrite_payload = _as_dict(item, "overwrite must be object", ow_path)
        _ensure_known_keys(overwrite_payload, _ALLOWED_OVERWRITE_KEYS, ow_path)
        _require_keys(overwrite_payload, {"target"}, ow_path)

        target_payload = _as_dict(
            overwrite_payload["target"], "target must be object", f"{ow_path}.target"
        )
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
        typed_target_type = cast(OverwriteTargetType, target_type)
        items.append(
            PermissionOverwrite(
                target=OverwriteTarget(type=typed_target_type, id=target_id),
                allow=_list_of_str(
                    overwrite_payload.get("allow", []), f"{ow_path}.allow"
                ),
                deny=_list_of_str(overwrite_payload.get("deny", []), f"{ow_path}.deny"),
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


def _ensure_known_keys(
    payload: dict[str, object], allowed: set[str], path: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        location = path or "<root>"
        raise SchemaValidationError(
            f"unknown keys: {', '.join(unknown)}",
            location,
        )


def _require_keys(payload: dict[str, object], required: set[str], path: str) -> None:
    missing = sorted(key for key in required if key not in payload)
    if missing:
        location = path or "<root>"
        raise SchemaValidationError(
            f"missing required keys: {', '.join(missing)}",
            location,
        )


def _required_str(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise SchemaValidationError("must be non-empty string", path)
    return value


def _opt_str(value: object, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaValidationError("must be string", path)
    return value


def _opt_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaValidationError("must be integer", path)
    return value


def _opt_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise SchemaValidationError("must be boolean", path)
    return value


def _list_of_str(value: object, path: str) -> list[str]:
    values = _as_list(value, "must be array", path)
    result: list[str] = []
    for idx, item in enumerate(values):
        if not isinstance(item, str):
            raise SchemaValidationError("array values must be string", f"{path}[{idx}]")
        result.append(item)
    return result


def _as_dict(value: object, message: str, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SchemaValidationError(message, path)
    return cast(dict[str, object], value)


def _as_list(value: object, message: str, path: str) -> list[object]:
    if not isinstance(value, list):
        raise SchemaValidationError(message, path)
    return cast(list[object], value)
