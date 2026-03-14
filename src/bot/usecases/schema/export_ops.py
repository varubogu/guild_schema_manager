from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal runtime
    yaml = None

from bot.usecases.schema_model.models import GuildSchema, PermissionOverwrite

from .models import ExportFieldSelection


def prepend_schema_hint_comment(yaml_text: str, schema_url: str) -> str:
    hint = f"# yaml-language-server: $schema={schema_url}"
    return f"{hint}\n\n{yaml_text}"


def build_result_markdown_filename(schema: GuildSchema, *, suffix: str) -> str:
    base = _build_export_filename_base(schema)
    return f"{base}_{suffix}.md"


def build_export_filename(schema: GuildSchema) -> str:
    return f"{_build_export_filename_base(schema)}.yaml"


def is_filtered_export(selection: ExportFieldSelection) -> bool:
    return not (
        selection.include_name
        and selection.include_permissions
        and selection.include_role_overwrites
        and selection.include_other_settings
    )


def dump_mapping_yaml(payload: dict[str, object]) -> str:
    if yaml is not None:
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_export_payload(
    schema: GuildSchema,
    selection: ExportFieldSelection,
) -> dict[str, object]:
    guild_payload: dict[str, object] = {"id": schema.guild.id}
    if selection.include_name:
        guild_payload["name"] = schema.guild.name

    roles_payload: list[dict[str, object]] = []
    for role in schema.roles:
        role_payload: dict[str, object] = {"id": _export_id(role.id)}
        if selection.include_name:
            role_payload["name"] = role.name
        if selection.include_permissions:
            role_payload["permissions"] = role.permissions
        if selection.include_other_settings:
            role_payload["bot_managed"] = role.bot_managed
            role_payload["color"] = role.color
            role_payload["hoist"] = role.hoist
            role_payload["mentionable"] = role.mentionable
            role_payload["position"] = role.position
        roles_payload.append(role_payload)

    categories_payload: list[dict[str, object]] = []
    for category in schema.categories:
        category_payload: dict[str, object] = {"id": _export_id(category.id)}
        if selection.include_name:
            category_payload["name"] = category.name
        if selection.include_role_overwrites or selection.include_other_settings:
            category_payload["overwrites"] = _export_overwrites(
                category.overwrites,
                include_role_targets=selection.include_role_overwrites,
                include_member_targets=selection.include_other_settings,
            )
        if selection.include_other_settings:
            category_payload["position"] = category.position
        categories_payload.append(category_payload)

    channels_payload: list[dict[str, object]] = []
    for channel in schema.channels:
        channel_payload: dict[str, object] = {"id": _export_id(channel.id)}
        if selection.include_name:
            channel_payload["name"] = channel.name
        if selection.include_role_overwrites or selection.include_other_settings:
            channel_payload["overwrites"] = _export_overwrites(
                channel.overwrites,
                include_role_targets=selection.include_role_overwrites,
                include_member_targets=selection.include_other_settings,
            )
        if selection.include_other_settings:
            channel_payload["type"] = channel.type
            if channel.parent_id is not None:
                channel_payload["parent_id"] = channel.parent_id
            if channel.parent_name is not None:
                channel_payload["parent_name"] = channel.parent_name
            channel_payload["position"] = channel.position
            if channel.topic is not None:
                channel_payload["topic"] = channel.topic
            channel_payload["nsfw"] = channel.nsfw
            channel_payload["slowmode_delay"] = channel.slowmode_delay
        channels_payload.append(channel_payload)

    return {
        "version": schema.version,
        "guild": guild_payload,
        "roles": roles_payload,
        "categories": categories_payload,
        "channels": channels_payload,
    }


def _build_export_filename_base(schema: GuildSchema) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{schema.guild.name}-{timestamp}"


def _export_id(raw_id: str | None) -> str:
    return raw_id or ""


def _export_overwrites(
    overwrites: Sequence[PermissionOverwrite],
    *,
    include_role_targets: bool,
    include_member_targets: bool,
) -> list[dict[str, object]]:
    exported_overwrites: list[dict[str, object]] = []
    for overwrite in overwrites:
        target = getattr(overwrite, "target", None)
        target_type = getattr(target, "type", None)
        if target_type == "role" and not include_role_targets:
            continue
        if target_type == "member" and not include_member_targets:
            continue
        if target_type not in {"role", "member"}:
            continue
        exported_overwrites.append(
            {
                "target": {
                    "type": str(target_type),
                    "id": str(getattr(target, "id", "")),
                },
                "allow": list(getattr(overwrite, "allow", [])),
                "deny": list(getattr(overwrite, "deny", [])),
            }
        )
    return exported_overwrites


__all__ = [
    "build_export_filename",
    "build_export_payload",
    "build_result_markdown_filename",
    "dump_mapping_yaml",
    "is_filtered_export",
    "prepend_schema_hint_comment",
]
