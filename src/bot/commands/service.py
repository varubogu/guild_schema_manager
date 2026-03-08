from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, cast

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal runtime
    yaml = None

from bot.diff import DiffValidationError, diff_schemas
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
from bot.schema.models import GuildSchema, PermissionOverwrite
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
        locale: SupportedLocale = "en",
    ) -> DiffResponse:
        require_guild_admin(invoker_is_admin, locale=locale)
        if file_trust_mode:
            desired = parse_schema_yaml(uploaded)
        else:
            desired = parse_schema_patch_yaml(uploaded, current)
        result = diff_schemas(current, desired)
        return DiffResponse(markdown=render_diff_markdown(result, locale=locale))

    def apply_schema_preview(
        self,
        current: GuildSchema,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        invoker_id: int,
        file_trust_mode: bool = False,
        locale: SupportedLocale = "en",
    ) -> ApplyPreviewResponse:
        require_guild_admin(invoker_is_admin, locale=locale)
        if file_trust_mode:
            desired = parse_schema_yaml(uploaded)
        else:
            desired = parse_schema_patch_yaml(uploaded, current)
        diff_result = diff_schemas(current, desired)

        if not diff_result.changes:
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


def _build_export_filename(schema: GuildSchema) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{schema.guild.name}-{timestamp}.yaml"


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


def parse_uploaded_schema(
    uploaded: bytes,
    *,
    current: GuildSchema | None = None,
    file_trust_mode: bool = False,
) -> GuildSchema:
    try:
        if file_trust_mode:
            return parse_schema_yaml(uploaded)
        if current is not None:
            return parse_schema_patch_yaml(uploaded, current)
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
