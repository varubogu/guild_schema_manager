from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable, cast

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal runtime
    yaml = None

from bot.diff import DiffInformationalChange, DiffValidationError, diff_schemas
from bot.diff.models import DiffInformationalAction, DiffTargetType
from bot.executor import (
    AsyncOperationExecutor,
    OperationExecutor,
    execute_plan,
    execute_plan_async,
)
from bot.localization import SupportedLocale, t
from bot.planner import ApplyReport, build_apply_plan
from bot.rendering import render_apply_report, render_diff_markdown
from bot.schema.errors import SchemaValidationError
from bot.schema.models import (
    CategorySchema,
    ChannelSchema,
    GuildSchema,
    PermissionOverwrite,
    RoleSchema,
)
from bot.schema.parser import parse_schema_patch_yaml, parse_schema_yaml, schema_to_yaml
from bot.security import ensure_invoker_only, require_guild_admin
from bot.session_store import (
    InMemorySessionStore,
    SessionError,
    SessionExpiredError,
    SessionForbiddenError,
    SessionNotFoundError,
)


@dataclass(slots=True)
class FilePayload:
    filename: str
    content: bytes


@dataclass(slots=True)
class ExportResponse:
    markdown: str
    file: FilePayload


@dataclass(slots=True)
class DiffResponse:
    markdown: str


@dataclass(slots=True, frozen=True)
class ExportFieldSelection:
    include_name: bool = True
    include_permissions: bool = True
    include_role_overwrites: bool = True
    include_other_settings: bool = True


@dataclass(slots=True)
class ApplyPreviewResponse:
    markdown: str
    confirmation_token: str | None


@dataclass(slots=True)
class ApplyExecutionResponse:
    markdown: str
    backup_file: FilePayload | None
    report: ApplyReport | None


class SchemaCommandService:
    def __init__(
        self,
        session_store: InMemorySessionStore,
        executor_factory: Callable[[], OperationExecutor],
        *,
        schema_hint_url_template: str | None = None,
    ) -> None:
        self._session_store = session_store
        self._executor_factory = executor_factory
        self._schema_hint_url_template = schema_hint_url_template

    def export_schema(
        self,
        current: GuildSchema,
        *,
        invoker_is_admin: bool,
        fields: ExportFieldSelection | None = None,
        locale: SupportedLocale = "en",
    ) -> ExportResponse:
        require_guild_admin(invoker_is_admin, locale=locale)
        selection = fields or ExportFieldSelection()
        export_payload = _build_export_payload(current, selection)
        yaml_text = _dump_yaml(export_payload)
        schema_url = self._schema_url_for_version(current.version)
        if schema_url is not None:
            yaml_text = _prepend_schema_hint_comment(yaml_text, schema_url)
        summary = t(
            "service.export.summary",
            locale,
            roles=len(current.roles),
            categories=len(current.categories),
            channels=len(current.channels),
        )
        if _is_filtered_export(selection):
            summary += f" {t('service.export.filtered_suffix', locale)}"
        return ExportResponse(
            markdown=summary,
            file=FilePayload(
                filename=_build_export_filename(current),
                content=yaml_text.encode("utf-8"),
            ),
        )

    def diff_schema(
        self,
        current: GuildSchema,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        file_trust_mode: bool = False,
        prefer_name_matching: bool = False,
        locale: SupportedLocale = "en",
    ) -> DiffResponse:
        require_guild_admin(invoker_is_admin, locale=locale)
        uploaded_payload = _try_load_uploaded_mapping(uploaded)
        if file_trust_mode:
            desired = parse_schema_yaml(
                uploaded,
                strict_relationship_validation=False,
            )
        else:
            desired = parse_schema_patch_yaml(
                uploaded,
                current,
                prefer_name_matching=prefer_name_matching,
                allow_ambiguous_name_match=True,
                strict_relationship_validation=False,
            )
        result = diff_schemas(
            current,
            desired,
            prefer_name_matching=prefer_name_matching,
            allow_ambiguous_name_match=True,
        )
        result.informational_changes = _build_informational_changes(
            current,
            desired,
            file_trust_mode=file_trust_mode,
            prefer_name_matching=prefer_name_matching,
            uploaded_payload=uploaded_payload,
        )
        return DiffResponse(markdown=render_diff_markdown(result, locale=locale))

    def apply_schema_preview(
        self,
        current: GuildSchema,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        invoker_id: int,
        file_trust_mode: bool = False,
        prefer_name_matching: bool = False,
        locale: SupportedLocale = "en",
    ) -> ApplyPreviewResponse:
        require_guild_admin(invoker_is_admin, locale=locale)
        uploaded_payload = _try_load_uploaded_mapping(uploaded)
        if file_trust_mode:
            desired = parse_schema_yaml(uploaded)
        else:
            desired = parse_schema_patch_yaml(
                uploaded,
                current,
                prefer_name_matching=prefer_name_matching,
            )
        diff_result = diff_schemas(
            current,
            desired,
            prefer_name_matching=prefer_name_matching,
        )
        diff_result.informational_changes = _build_informational_changes(
            current,
            desired,
            file_trust_mode=file_trust_mode,
            prefer_name_matching=prefer_name_matching,
            uploaded_payload=uploaded_payload,
        )

        if not diff_result.changes:
            if diff_result.informational_changes:
                return ApplyPreviewResponse(
                    markdown=render_diff_markdown(diff_result, locale=locale),
                    confirmation_token=None,
                )
            return ApplyPreviewResponse(
                markdown=t("service.apply.no_changes", locale),
                confirmation_token=None,
            )

        plan = build_apply_plan(diff_result)
        pending = self._session_store.create(
            invoker_id=invoker_id,
            desired_schema=desired,
            diff_result=diff_result,
            apply_plan=plan,
        )
        preview = render_diff_markdown(diff_result, locale=locale)
        preview += "\n\n" + t(
            "service.apply.confirmation_token",
            locale,
            token=pending.token,
        )
        return ApplyPreviewResponse(markdown=preview, confirmation_token=pending.token)

    def confirm_apply(
        self,
        token: str,
        *,
        invoker_id: int,
        current: GuildSchema,
        locale: SupportedLocale = "en",
    ) -> ApplyExecutionResponse:
        try:
            pending = self._session_store.consume(token, invoker_id)
        except SessionNotFoundError:
            return ApplyExecutionResponse(
                markdown=t("service.apply.session_not_found", locale),
                backup_file=None,
                report=None,
            )
        except SessionExpiredError:
            return ApplyExecutionResponse(
                markdown=t("service.apply.session_expired", locale),
                backup_file=None,
                report=None,
            )
        except SessionForbiddenError:
            return ApplyExecutionResponse(
                markdown=t("service.apply.session_forbidden", locale),
                backup_file=None,
                report=None,
            )
        except SessionError as exc:
            return ApplyExecutionResponse(
                markdown=t("service.apply.session_error", locale, error=str(exc)),
                backup_file=None,
                report=None,
            )

        ensure_invoker_only(invoker_id, pending.invoker_id, locale=locale)

        backup = schema_to_yaml(current).encode("utf-8")
        executor = self._executor_factory()
        report = execute_plan(
            plan=pending.apply_plan, backup_file=backup, executor=executor
        )
        markdown = render_apply_report(report, locale=locale)
        return ApplyExecutionResponse(
            markdown=markdown,
            backup_file=FilePayload(
                filename="guild-schema-backup.yaml", content=backup
            ),
            report=report,
        )

    async def confirm_apply_async(
        self,
        token: str,
        *,
        invoker_id: int,
        current: GuildSchema,
        executor: AsyncOperationExecutor,
        locale: SupportedLocale = "en",
    ) -> ApplyExecutionResponse:
        try:
            pending = self._session_store.consume(token, invoker_id)
        except SessionNotFoundError:
            return ApplyExecutionResponse(
                markdown=t("service.apply.session_not_found", locale),
                backup_file=None,
                report=None,
            )
        except SessionExpiredError:
            return ApplyExecutionResponse(
                markdown=t("service.apply.session_expired", locale),
                backup_file=None,
                report=None,
            )
        except SessionForbiddenError:
            return ApplyExecutionResponse(
                markdown=t("service.apply.session_forbidden", locale),
                backup_file=None,
                report=None,
            )
        except SessionError as exc:
            return ApplyExecutionResponse(
                markdown=t("service.apply.session_error", locale, error=str(exc)),
                backup_file=None,
                report=None,
            )

        ensure_invoker_only(invoker_id, pending.invoker_id, locale=locale)

        backup = schema_to_yaml(current).encode("utf-8")
        report = await execute_plan_async(
            plan=pending.apply_plan, backup_file=backup, executor=executor
        )
        markdown = render_apply_report(report, locale=locale)
        return ApplyExecutionResponse(
            markdown=markdown,
            backup_file=FilePayload(
                filename="guild-schema-backup.yaml", content=backup
            ),
            report=report,
        )

    def _schema_url_for_version(self, version: int) -> str | None:
        if self._schema_hint_url_template is None:
            return None
        return self._schema_hint_url_template.replace("{version}", str(version))


def _prepend_schema_hint_comment(yaml_text: str, schema_url: str) -> str:
    hint = f"# yaml-language-server: $schema={schema_url}"
    return f"{hint}\n\n{yaml_text}"


def build_result_markdown_filename(schema: GuildSchema, *, suffix: str) -> str:
    base = _build_export_filename_base(schema)
    return f"{base}_{suffix}.md"


def _build_export_filename(schema: GuildSchema) -> str:
    return f"{_build_export_filename_base(schema)}.yaml"


def _build_export_filename_base(schema: GuildSchema) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{schema.guild.name}-{timestamp}"


def _is_filtered_export(selection: ExportFieldSelection) -> bool:
    return not (
        selection.include_name
        and selection.include_permissions
        and selection.include_role_overwrites
        and selection.include_other_settings
    )


def _dump_yaml(payload: dict[str, object]) -> str:
    if yaml is not None:
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _build_export_payload(
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


def _try_load_uploaded_mapping(uploaded: bytes | str) -> dict[str, object] | None:
    try:
        payload = _load_uploaded_mapping(uploaded)
    except ValueError:
        return None
    _populate_channel_parent_names_from_uploaded_payload(payload)
    return payload


def _build_informational_changes(
    current: GuildSchema,
    desired: GuildSchema,
    *,
    file_trust_mode: bool,
    prefer_name_matching: bool,
    uploaded_payload: dict[str, object] | None,
) -> list[DiffInformationalChange]:
    informational: list[DiffInformationalChange] = []
    current_category_name_by_id = _category_name_by_id(current.categories)
    desired_category_name_by_id = _category_name_by_id(desired.categories)

    role_pairs = _match_named_entities(
        current.roles,
        desired.roles,
        prefer_name_matching=prefer_name_matching,
    )
    role_defined = (
        set(range(len(current.roles)))
        if file_trust_mode
        else _defined_named_entity_indices(
            current.roles,
            uploaded_payload,
            "roles",
            prefer_name_matching=prefer_name_matching,
        )
    )
    informational.extend(
        _informational_for_roles(
            current.roles,
            desired.roles,
            role_pairs,
            role_defined,
        )
    )

    category_pairs = _match_named_entities(
        current.categories,
        desired.categories,
        prefer_name_matching=prefer_name_matching,
    )
    category_defined = (
        set(range(len(current.categories)))
        if file_trust_mode
        else _defined_named_entity_indices(
            current.categories,
            uploaded_payload,
            "categories",
            prefer_name_matching=prefer_name_matching,
        )
    )
    informational.extend(
        _informational_for_categories(
            current.categories,
            desired.categories,
            category_pairs,
            category_defined,
        )
    )

    channel_pairs = _match_channels(
        current.channels,
        desired.channels,
        prefer_name_matching=prefer_name_matching,
        current_category_name_by_id=current_category_name_by_id,
        desired_category_name_by_id=desired_category_name_by_id,
    )
    channel_defined = (
        set(range(len(current.channels)))
        if file_trust_mode
        else _defined_channel_indices(
            current.channels,
            uploaded_payload,
            prefer_name_matching=prefer_name_matching,
            current_category_name_by_id=current_category_name_by_id,
        )
    )
    informational.extend(
        _informational_for_channels(
            current.channels,
            desired.channels,
            channel_pairs,
            channel_defined,
            prefer_name_matching=prefer_name_matching,
            current_category_name_by_id=current_category_name_by_id,
            desired_category_name_by_id=desired_category_name_by_id,
        )
    )
    return informational


def _match_named_entities(
    current_items: Sequence[RoleSchema | CategorySchema],
    desired_items: Sequence[RoleSchema | CategorySchema],
    *,
    prefer_name_matching: bool,
) -> list[tuple[int, int]]:
    unmatched_current = set(range(len(current_items)))
    by_id: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for idx, item in enumerate(current_items):
        if item.id:
            by_id[item.id] = idx
        by_name.setdefault(item.name, []).append(idx)

    pairs: list[tuple[int, int]] = []
    for desired_idx, desired_item in enumerate(desired_items):
        current_idx: int | None = None
        if prefer_name_matching:
            current_idx = _first_matching_named_entity_index(
                current_items,
                by_name.get(desired_item.name, []),
                unmatched_current,
                desired_item,
            )
        else:
            if desired_item.id:
                candidate = by_id.get(desired_item.id)
                if candidate is not None and candidate in unmatched_current:
                    current_idx = candidate
            if current_idx is None:
                current_idx = _first_matching_named_entity_index(
                    current_items,
                    by_name.get(desired_item.name, []),
                    unmatched_current,
                    desired_item,
                )
        if current_idx is None:
            continue
        unmatched_current.remove(current_idx)
        pairs.append((current_idx, desired_idx))
    return pairs


def _match_channels(
    current_channels: Sequence[ChannelSchema],
    desired_channels: Sequence[ChannelSchema],
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    desired_category_name_by_id: dict[str, str],
) -> list[tuple[int, int]]:
    unmatched_current = set(range(len(current_channels)))
    by_id: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for idx, channel in enumerate(current_channels):
        if channel.id:
            by_id[channel.id] = idx
        by_name.setdefault(channel.name, []).append(idx)

    pairs: list[tuple[int, int]] = []
    for desired_idx, desired_channel in enumerate(desired_channels):
        current_idx: int | None = None
        if prefer_name_matching:
            current_idx = _first_matching_channel_index(
                current_channels,
                by_name.get(desired_channel.name, []),
                unmatched_current,
                desired_channel,
                prefer_name_matching=prefer_name_matching,
                current_category_name_by_id=current_category_name_by_id,
                desired_category_name_by_id=desired_category_name_by_id,
            )
        else:
            if desired_channel.id:
                candidate = by_id.get(desired_channel.id)
                if candidate is not None and candidate in unmatched_current:
                    current_idx = candidate
            if current_idx is None:
                current_idx = _first_matching_channel_index(
                    current_channels,
                    by_name.get(desired_channel.name, []),
                    unmatched_current,
                    desired_channel,
                    prefer_name_matching=prefer_name_matching,
                    current_category_name_by_id=current_category_name_by_id,
                    desired_category_name_by_id=desired_category_name_by_id,
                )

        if current_idx is None:
            continue
        unmatched_current.remove(current_idx)
        pairs.append((current_idx, desired_idx))
    return pairs


def _first_matching_channel_index(
    current_channels: Sequence[ChannelSchema],
    candidates: Sequence[int],
    unmatched_current: set[int],
    desired_channel: ChannelSchema,
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    desired_category_name_by_id: dict[str, str],
) -> int | None:
    desired_parent_scope = _channel_parent_scope(
        desired_channel,
        prefer_name_matching=prefer_name_matching,
        category_name_by_id=desired_category_name_by_id,
    )
    scoped_candidates: list[int] = []
    for candidate in candidates:
        if candidate not in unmatched_current:
            continue
        current_channel = current_channels[candidate]
        if current_channel.type != desired_channel.type:
            continue
        if desired_parent_scope is not None:
            current_parent_scope = _channel_parent_scope(
                current_channel,
                prefer_name_matching=prefer_name_matching,
                category_name_by_id=current_category_name_by_id,
            )
            if current_parent_scope != desired_parent_scope:
                continue
        scoped_candidates.append(candidate)

    if scoped_candidates:
        return scoped_candidates[0]
    return _first_unmatched_index(candidates, unmatched_current)


def _defined_named_entity_indices(
    current_items: Sequence[RoleSchema | CategorySchema],
    uploaded_payload: dict[str, object] | None,
    section: str,
    *,
    prefer_name_matching: bool,
) -> set[int]:
    if uploaded_payload is None:
        return set()
    raw_items = uploaded_payload.get(section)
    if not isinstance(raw_items, list):
        return set()

    by_id: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for idx, item in enumerate(current_items):
        if item.id:
            by_id[item.id] = idx
        by_name.setdefault(item.name, []).append(idx)

    unmatched_current = set(range(len(current_items)))
    defined: set[int] = set()
    for raw_item in cast(list[object], raw_items):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, object], raw_item)
        idx: int | None = None
        if prefer_name_matching:
            name = item.get("name")
            if isinstance(name, str) and name:
                idx = _first_matching_payload_named_entity_index(
                    current_items,
                    by_name.get(name, []),
                    unmatched_current,
                    item,
                    section=section,
                )
        else:
            raw_id = item.get("id")
            if isinstance(raw_id, str) and raw_id:
                candidate = by_id.get(raw_id)
                if candidate is not None and candidate in unmatched_current:
                    idx = candidate
            if idx is None:
                name = item.get("name")
                if isinstance(name, str) and name:
                    idx = _first_matching_payload_named_entity_index(
                        current_items,
                        by_name.get(name, []),
                        unmatched_current,
                        item,
                        section=section,
                    )
        if idx is None:
            continue
        defined.add(idx)
        unmatched_current.remove(idx)
    return defined


def _defined_channel_indices(
    current_channels: Sequence[ChannelSchema],
    uploaded_payload: dict[str, object] | None,
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
) -> set[int]:
    if uploaded_payload is None:
        return set()
    raw_channels = uploaded_payload.get("channels")
    if not isinstance(raw_channels, list):
        return set()

    by_id: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for idx, channel in enumerate(current_channels):
        if channel.id:
            by_id[channel.id] = idx
        by_name.setdefault(channel.name, []).append(idx)

    uploaded_category_name_by_id = _category_name_by_id_from_payload(uploaded_payload)
    unmatched_current = set(range(len(current_channels)))
    defined: set[int] = set()

    for raw_channel in cast(list[object], raw_channels):
        if not isinstance(raw_channel, dict):
            continue
        channel_payload = cast(dict[str, object], raw_channel)
        idx: int | None = None
        if prefer_name_matching:
            idx = _match_current_channel_from_payload(
                current_channels,
                channel_payload,
                by_name,
                unmatched_current,
                prefer_name_matching=prefer_name_matching,
                current_category_name_by_id=current_category_name_by_id,
                uploaded_category_name_by_id=uploaded_category_name_by_id,
            )
        else:
            raw_id = channel_payload.get("id")
            if isinstance(raw_id, str) and raw_id:
                candidate = by_id.get(raw_id)
                if candidate is not None and candidate in unmatched_current:
                    idx = candidate
            if idx is None:
                idx = _match_current_channel_from_payload(
                    current_channels,
                    channel_payload,
                    by_name,
                    unmatched_current,
                    prefer_name_matching=prefer_name_matching,
                    current_category_name_by_id=current_category_name_by_id,
                    uploaded_category_name_by_id=uploaded_category_name_by_id,
                )
        if idx is None:
            continue
        defined.add(idx)
        unmatched_current.remove(idx)
    return defined


def _match_current_channel_from_payload(
    current_channels: Sequence[ChannelSchema],
    channel_payload: dict[str, object],
    by_name: dict[str, list[int]],
    unmatched_current: set[int],
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    uploaded_category_name_by_id: dict[str, str],
) -> int | None:
    name = channel_payload.get("name")
    if not isinstance(name, str) or not name:
        return None

    payload_type = channel_payload.get("type")
    payload_parent_scope = _channel_parent_scope_from_payload(
        channel_payload,
        prefer_name_matching=prefer_name_matching,
        category_name_by_id=uploaded_category_name_by_id,
    )

    for candidate in by_name.get(name, []):
        if candidate not in unmatched_current:
            continue
        current_channel = current_channels[candidate]
        if (
            isinstance(payload_type, str)
            and payload_type
            and current_channel.type != payload_type
        ):
            continue
        if payload_parent_scope is not None:
            current_parent_scope = _channel_parent_scope(
                current_channel,
                prefer_name_matching=prefer_name_matching,
                category_name_by_id=current_category_name_by_id,
            )
            if current_parent_scope != payload_parent_scope:
                continue
        return candidate
    return None


def _informational_for_roles(
    current_roles: Sequence[RoleSchema],
    desired_roles: Sequence[RoleSchema],
    pairs: Sequence[tuple[int, int]],
    defined_indices: set[int],
) -> list[DiffInformationalChange]:
    rows: list[DiffInformationalChange] = []
    for current_idx, desired_idx in pairs:
        current_role = current_roles[current_idx]
        desired_role = desired_roles[desired_idx]
        if not _role_exact(current_role, desired_role):
            continue
        rows.append(
            _informational_change(
                target_type="role",
                target_id=current_role.id or desired_role.id,
                before_name=current_role.name,
                after_name=desired_role.name,
                before=_safe_schema_payload(current_role),
                after=_safe_schema_payload(desired_role),
                file_defined=current_idx in defined_indices,
            )
        )
    return rows


def _informational_for_categories(
    current_categories: Sequence[CategorySchema],
    desired_categories: Sequence[CategorySchema],
    pairs: Sequence[tuple[int, int]],
    defined_indices: set[int],
) -> list[DiffInformationalChange]:
    rows: list[DiffInformationalChange] = []
    for current_idx, desired_idx in pairs:
        current_category = current_categories[current_idx]
        desired_category = desired_categories[desired_idx]
        if not _category_exact(current_category, desired_category):
            continue
        rows.append(
            _informational_change(
                target_type="category",
                target_id=current_category.id or desired_category.id,
                before_name=current_category.name,
                after_name=desired_category.name,
                before=_safe_schema_payload(current_category),
                after=_safe_schema_payload(desired_category),
                file_defined=current_idx in defined_indices,
            )
        )
    return rows


def _informational_for_channels(
    current_channels: Sequence[ChannelSchema],
    desired_channels: Sequence[ChannelSchema],
    pairs: Sequence[tuple[int, int]],
    defined_indices: set[int],
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    desired_category_name_by_id: dict[str, str],
) -> list[DiffInformationalChange]:
    rows: list[DiffInformationalChange] = []
    for current_idx, desired_idx in pairs:
        current_channel = current_channels[current_idx]
        desired_channel = desired_channels[desired_idx]
        if not _channel_exact(
            current_channel,
            desired_channel,
            prefer_name_matching=prefer_name_matching,
            current_category_name_by_id=current_category_name_by_id,
            desired_category_name_by_id=desired_category_name_by_id,
        ):
            continue
        rows.append(
            _informational_change(
                target_type="channel",
                target_id=current_channel.id or desired_channel.id,
                before_name=current_channel.name,
                after_name=desired_channel.name,
                before=_safe_schema_payload(current_channel),
                after=_safe_schema_payload(desired_channel),
                file_defined=current_idx in defined_indices,
            )
        )
    return rows


def _informational_change(
    *,
    target_type: DiffTargetType,
    target_id: str | None,
    before_name: str | None,
    after_name: str | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    file_defined: bool,
) -> DiffInformationalChange:
    action: DiffInformationalAction = (
        "UnchangedExact" if file_defined else "UnchangedFileUndefined"
    )
    return DiffInformationalChange(
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
        before_name=before_name,
        after_name=after_name,
    )


def _role_exact(current: RoleSchema, desired: RoleSchema) -> bool:
    return (
        current.name == desired.name
        and current.bot_managed == desired.bot_managed
        and current.color == desired.color
        and current.hoist == desired.hoist
        and current.mentionable == desired.mentionable
        and sorted(current.permissions) == sorted(desired.permissions)
        and current.position == desired.position
    )


def _category_exact(current: CategorySchema, desired: CategorySchema) -> bool:
    return (
        current.name == desired.name
        and current.position == desired.position
        and _overwrites_equal(current.overwrites, desired.overwrites)
    )


def _channel_exact(
    current: ChannelSchema,
    desired: ChannelSchema,
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    desired_category_name_by_id: dict[str, str],
) -> bool:
    return (
        current.name == desired.name
        and current.type == desired.type
        and current.topic == desired.topic
        and current.nsfw == desired.nsfw
        and current.slowmode_delay == desired.slowmode_delay
        and current.position == desired.position
        and _channel_parent_scope(
            current,
            prefer_name_matching=prefer_name_matching,
            category_name_by_id=current_category_name_by_id,
        )
        == _channel_parent_scope(
            desired,
            prefer_name_matching=prefer_name_matching,
            category_name_by_id=desired_category_name_by_id,
        )
        and _overwrites_equal(current.overwrites, desired.overwrites)
    )


def _overwrites_equal(
    current_overwrites: Sequence[PermissionOverwrite],
    desired_overwrites: Sequence[PermissionOverwrite],
) -> bool:
    return _overwrite_map(current_overwrites) == _overwrite_map(desired_overwrites)


def _overwrite_map(
    overwrites: Sequence[PermissionOverwrite],
) -> dict[str, tuple[list[str], list[str]]]:
    mapped: dict[str, tuple[list[str], list[str]]] = {}
    for overwrite in overwrites:
        key = f"{overwrite.target.type}:{overwrite.target.id}"
        mapped[key] = (sorted(overwrite.allow), sorted(overwrite.deny))
    return mapped


def _safe_schema_payload(
    value: RoleSchema | CategorySchema | ChannelSchema,
) -> dict[str, object]:
    payload = cast(dict[str, object], asdict(value))
    if "permissions" in payload:
        permissions = payload.get("permissions")
        if isinstance(permissions, list):
            payload["permissions"] = sorted(
                str(item) for item in cast(list[object], permissions)
            )
    if "overwrites" in payload:
        raw_overwrites = payload.get("overwrites")
        if isinstance(raw_overwrites, list):
            normalized: list[dict[str, object]] = []
            for raw_overwrite in cast(list[object], raw_overwrites):
                if not isinstance(raw_overwrite, dict):
                    continue
                overwrite = dict(cast(dict[str, object], raw_overwrite))
                allow = overwrite.get("allow")
                deny = overwrite.get("deny")
                if isinstance(allow, list):
                    overwrite["allow"] = sorted(
                        str(item) for item in cast(list[object], allow)
                    )
                if isinstance(deny, list):
                    overwrite["deny"] = sorted(
                        str(item) for item in cast(list[object], deny)
                    )
                normalized.append(overwrite)
            payload["overwrites"] = sorted(
                normalized,
                key=_overwrite_sort_key,
            )
    return payload


def _overwrite_sort_key(item: dict[str, object]) -> str:
    target = item.get("target")
    if not isinstance(target, dict):
        return ":"
    target_payload = cast(dict[str, object], target)
    return f"{target_payload.get('type', '')}:{target_payload.get('id', '')}"


def _category_name_by_id(categories: Sequence[CategorySchema]) -> dict[str, str]:
    return {category.id: category.name for category in categories if category.id}


def _category_name_by_id_from_payload(payload: dict[str, object]) -> dict[str, str]:
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


def _populate_channel_parent_names_from_uploaded_payload(
    payload: dict[str, object],
) -> None:
    category_name_by_id = _category_name_by_id_from_payload(payload)
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


def _channel_parent_scope(
    channel: ChannelSchema,
    *,
    prefer_name_matching: bool,
    category_name_by_id: dict[str, str],
) -> str | None:
    if prefer_name_matching:
        if channel.parent_name:
            return channel.parent_name
        if channel.parent_id:
            return category_name_by_id.get(channel.parent_id)
        return None
    return channel.parent_id or channel.parent_name


def _channel_parent_scope_from_payload(
    payload: dict[str, object],
    *,
    prefer_name_matching: bool,
    category_name_by_id: dict[str, str],
) -> str | None:
    if prefer_name_matching:
        parent_name = payload.get("parent_name")
        if isinstance(parent_name, str) and parent_name:
            return parent_name
        parent_id = payload.get("parent_id")
        if isinstance(parent_id, str) and parent_id:
            return category_name_by_id.get(parent_id)
        return None

    parent_id = payload.get("parent_id")
    if isinstance(parent_id, str) and parent_id:
        return parent_id
    parent_name = payload.get("parent_name")
    if isinstance(parent_name, str) and parent_name:
        return parent_name
    return None


def _first_unmatched_index(
    candidates: Sequence[int],
    unmatched_current: set[int],
) -> int | None:
    for candidate in candidates:
        if candidate in unmatched_current:
            return candidate
    return None


def _first_matching_named_entity_index(
    current_items: Sequence[RoleSchema | CategorySchema],
    candidates: Sequence[int],
    unmatched_current: set[int],
    desired_item: RoleSchema | CategorySchema,
) -> int | None:
    unmatched_candidates = [
        candidate for candidate in candidates if candidate in unmatched_current
    ]
    if not unmatched_candidates:
        return None
    if isinstance(desired_item, RoleSchema):
        preferred: list[int] = []
        for candidate in unmatched_candidates:
            current_item = current_items[candidate]
            if not isinstance(current_item, RoleSchema):
                continue
            if current_item.bot_managed != desired_item.bot_managed:
                continue
            preferred.append(candidate)
        if preferred:
            return preferred[0]
    return unmatched_candidates[0]


def _first_matching_payload_named_entity_index(
    current_items: Sequence[RoleSchema | CategorySchema],
    candidates: Sequence[int],
    unmatched_current: set[int],
    payload: dict[str, object],
    *,
    section: str,
) -> int | None:
    unmatched_candidates = [
        candidate for candidate in candidates if candidate in unmatched_current
    ]
    if not unmatched_candidates:
        return None
    if section == "roles":
        desired_bot_managed = payload.get("bot_managed")
        if isinstance(desired_bot_managed, bool):
            preferred: list[int] = []
            for candidate in unmatched_candidates:
                current_item = current_items[candidate]
                if not isinstance(current_item, RoleSchema):
                    continue
                if current_item.bot_managed != desired_bot_managed:
                    continue
                preferred.append(candidate)
            if preferred:
                return preferred[0]
    return unmatched_candidates[0]


def parse_uploaded_schema(
    uploaded: bytes,
    *,
    current: GuildSchema | None = None,
    file_trust_mode: bool = False,
    prefer_name_matching: bool = False,
) -> GuildSchema:
    try:
        if file_trust_mode:
            return parse_schema_yaml(uploaded)
        if current is not None:
            return parse_schema_patch_yaml(
                uploaded,
                current,
                prefer_name_matching=prefer_name_matching,
            )
        return parse_schema_yaml(uploaded)
    except (SchemaValidationError, DiffValidationError) as exc:
        raise ValueError(str(exc)) from exc


def extract_uploaded_guild_id(uploaded: bytes | str) -> str | None:
    try:
        payload = _load_uploaded_mapping(uploaded)
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
    payload = _load_uploaded_mapping(uploaded)
    guild_value = payload.get("guild")
    guild_payload: dict[str, object] = {}
    if isinstance(guild_value, dict):
        guild_payload = dict(cast(dict[str, object], guild_value))
    guild_payload["id"] = guild_id
    payload["guild"] = guild_payload
    return _dump_yaml(payload).encode("utf-8")


def _load_uploaded_mapping(uploaded: bytes | str) -> dict[str, object]:
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
