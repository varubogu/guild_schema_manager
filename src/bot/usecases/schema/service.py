from __future__ import annotations

from copy import deepcopy
from typing import Callable
from typing import cast

from bot.localization import SupportedLocale, t
from bot.session_store import (
    InMemorySessionStore,
    PendingApplySession,
    SessionError,
    SessionExpiredError,
    SessionForbiddenError,
    SessionNotFoundError,
)
from bot.usecases.diff import diff_schemas
from bot.usecases.diff.models import DiffChange, DiffInformationalChange, DiffResult
from bot.usecases.executor import (
    AsyncOperationExecutor,
    OperationExecutor,
    execute_plan,
    execute_plan_async,
)
from bot.usecases.planner import build_apply_plan
from bot.usecases.rendering import render_apply_report, render_diff_markdown
from bot.usecases.schema_model.models import GuildSchema, RoleSchema
from bot.usecases.schema_model.parser import (
    parse_schema_patch_yaml,
    parse_schema_yaml,
    schema_to_yaml,
)
from bot.usecases.security import ensure_invoker_only, require_guild_admin

from .export_ops import (
    build_export_filename,
    build_export_payload,
    build_result_markdown_filename,
    dump_mapping_yaml,
    is_filtered_export,
    prepend_schema_hint_comment,
)
from .informational import build_informational_changes
from .models import (
    ApplyExecutionResponse,
    ApplyPreviewResponse,
    DiffResponse,
    ExportFieldSelection,
    ExportResponse,
    FilePayload,
)
from .uploaded_payload import try_load_uploaded_mapping

_ROLE_HIERARCHY_SKIP_REASON = "role_hierarchy_restriction"
_ROLE_HIERARCHY_SKIP_ACTIONS = frozenset({"Update", "Reorder"})


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
        yaml_text = dump_mapping_yaml(build_export_payload(current, selection))
        schema_url = self._schema_url_for_version(current.version)
        if schema_url is not None:
            yaml_text = prepend_schema_hint_comment(yaml_text, schema_url)

        summary = t(
            "service.export.summary",
            locale,
            roles=len(current.roles),
            categories=len(current.categories),
            channels=len(current.channels),
        )
        if is_filtered_export(selection):
            summary += f" {t('service.export.filtered_suffix', locale)}"

        return ExportResponse(
            markdown=summary,
            file=FilePayload(
                filename=build_export_filename(current),
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
        bot_top_role_position: int | None = None,
        locale: SupportedLocale = "en",
    ) -> DiffResponse:
        require_guild_admin(invoker_is_admin, locale=locale)

        uploaded_payload = try_load_uploaded_mapping(uploaded)
        desired = (
            parse_schema_yaml(
                uploaded,
                strict_relationship_validation=False,
            )
            if file_trust_mode
            else parse_schema_patch_yaml(
                uploaded,
                current,
                prefer_name_matching=prefer_name_matching,
                allow_ambiguous_name_match=True,
                strict_relationship_validation=False,
            )
        )

        result = diff_schemas(
            current,
            desired,
            prefer_name_matching=prefer_name_matching,
            allow_ambiguous_name_match=True,
        )
        result.informational_changes = build_informational_changes(
            current,
            desired,
            file_trust_mode=file_trust_mode,
            prefer_name_matching=prefer_name_matching,
            uploaded_payload=uploaded_payload,
        )
        _attach_uploaded_config_columns(
            result,
            uploaded_payload=uploaded_payload,
            prefer_name_matching=prefer_name_matching,
        )
        markdown = _build_diff_preview_markdown(
            diff_result=result,
            current=current,
            bot_top_role_position=bot_top_role_position,
            locale=locale,
        )
        return DiffResponse(markdown=markdown)

    def apply_schema_preview(
        self,
        current: GuildSchema,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        invoker_id: int,
        file_trust_mode: bool = False,
        prefer_name_matching: bool = False,
        bot_top_role_position: int | None = None,
        locale: SupportedLocale = "en",
    ) -> ApplyPreviewResponse:
        require_guild_admin(invoker_is_admin, locale=locale)

        uploaded_payload = try_load_uploaded_mapping(uploaded)
        desired = (
            parse_schema_yaml(
                uploaded,
                strict_relationship_validation=False,
            )
            if file_trust_mode
            else parse_schema_patch_yaml(
                uploaded,
                current,
                prefer_name_matching=prefer_name_matching,
                allow_ambiguous_name_match=True,
                strict_relationship_validation=False,
            )
        )

        diff_result = diff_schemas(
            current,
            desired,
            prefer_name_matching=prefer_name_matching,
            allow_ambiguous_name_match=True,
        )
        diff_result.informational_changes = build_informational_changes(
            current,
            desired,
            file_trust_mode=file_trust_mode,
            prefer_name_matching=prefer_name_matching,
            uploaded_payload=uploaded_payload,
        )
        _attach_uploaded_config_columns(
            diff_result,
            uploaded_payload=uploaded_payload,
            prefer_name_matching=prefer_name_matching,
        )

        if not diff_result.changes:
            return ApplyPreviewResponse(
                markdown=render_diff_markdown(diff_result, locale=locale),
                confirmation_token=None,
            )

        plan = build_apply_plan(diff_result)
        pending = self._session_store.create(
            invoker_id=invoker_id,
            desired_schema=desired,
            diff_result=diff_result,
            apply_plan=plan,
        )
        preview = _build_diff_preview_markdown(
            diff_result=diff_result,
            current=current,
            bot_top_role_position=bot_top_role_position,
            locale=locale,
        )
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
        pending_or_error = self._consume_pending_session(
            token=token,
            invoker_id=invoker_id,
            locale=locale,
        )
        if isinstance(pending_or_error, ApplyExecutionResponse):
            return pending_or_error

        ensure_invoker_only(invoker_id, pending_or_error.invoker_id, locale=locale)
        backup = schema_to_yaml(current).encode("utf-8")
        report = execute_plan(
            plan=pending_or_error.apply_plan,
            backup_file=backup,
            executor=self._executor_factory(),
        )
        return ApplyExecutionResponse(
            markdown=render_apply_report(report, locale=locale),
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
        pending_or_error = self._consume_pending_session(
            token=token,
            invoker_id=invoker_id,
            locale=locale,
        )
        if isinstance(pending_or_error, ApplyExecutionResponse):
            return pending_or_error

        ensure_invoker_only(invoker_id, pending_or_error.invoker_id, locale=locale)
        backup = schema_to_yaml(current).encode("utf-8")
        report = await execute_plan_async(
            plan=pending_or_error.apply_plan,
            backup_file=backup,
            executor=executor,
        )
        return ApplyExecutionResponse(
            markdown=render_apply_report(report, locale=locale),
            backup_file=FilePayload(
                filename="guild-schema-backup.yaml", content=backup
            ),
            report=report,
        )

    def _consume_pending_session(
        self,
        *,
        token: str,
        invoker_id: int,
        locale: SupportedLocale,
    ) -> PendingApplySession | ApplyExecutionResponse:
        try:
            return self._session_store.consume(token, invoker_id)
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

    def _schema_url_for_version(self, version: int) -> str | None:
        if self._schema_hint_url_template is None:
            return None
        return self._schema_hint_url_template.replace("{version}", str(version))


def _build_diff_preview_markdown(
    *,
    diff_result: DiffResult,
    current: GuildSchema,
    bot_top_role_position: int | None,
    locale: SupportedLocale,
) -> str:
    return render_diff_markdown(
        diff_result,
        locale=locale,
        expected_skip_reasons=_expected_skip_reasons_for_changes(
            diff_result,
            current=current,
            bot_top_role_position=bot_top_role_position,
        ),
    )


def _expected_skip_reasons_for_changes(
    diff_result: DiffResult,
    *,
    current: GuildSchema,
    bot_top_role_position: int | None,
) -> list[str | None]:
    reasons: list[str | None] = []
    for change in diff_result.changes:
        reason = _extract_apply_skip_reason(change)
        if reason is None:
            reason = _predict_role_hierarchy_skip_for_change(
                change,
                current=current,
                bot_top_role_position=bot_top_role_position,
            )
        reasons.append(reason)
    return reasons


def _predict_role_hierarchy_skip_for_change(
    change: DiffChange,
    *,
    current: GuildSchema,
    bot_top_role_position: int | None,
) -> str | None:
    if bot_top_role_position is None:
        return None
    if change.target_type != "role":
        return None
    if change.action not in _ROLE_HIERARCHY_SKIP_ACTIONS:
        return None
    role = _find_role_for_change(current.roles, change)
    if role is None:
        return None
    if role.position >= bot_top_role_position:
        return _ROLE_HIERARCHY_SKIP_REASON
    return None


def _find_role_for_change(
    current_roles: list[RoleSchema],
    change: DiffChange,
) -> RoleSchema | None:
    if change.target_id:
        for role in current_roles:
            if role.id == change.target_id:
                return role
    for name in (
        (change.before or {}).get("name"),
        (change.after or {}).get("name"),
    ):
        if not isinstance(name, str) or not name:
            continue
        for role in current_roles:
            if role.name == name:
                return role
    return None


def _extract_apply_skip_reason(change: DiffChange) -> str | None:
    for payload in (change.after, change.before):
        if payload is None:
            continue
        reason = payload.get("apply_excluded_reason")
        if isinstance(reason, str) and reason:
            return reason
    return None


def _attach_uploaded_config_columns(
    diff_result: DiffResult,
    *,
    uploaded_payload: dict[str, object] | None,
    prefer_name_matching: bool,
) -> None:
    if uploaded_payload is None:
        return

    for change in diff_result.changes:
        config_payload, config_name = _resolve_uploaded_config_for_row(
            change,
            uploaded_payload=uploaded_payload,
            prefer_name_matching=prefer_name_matching,
        )
        change.config = config_payload
        change.config_name = config_name

    for change in diff_result.informational_changes:
        config_payload, config_name = _resolve_uploaded_config_for_row(
            change,
            uploaded_payload=uploaded_payload,
            prefer_name_matching=prefer_name_matching,
        )
        change.config = config_payload
        change.config_name = config_name


def _resolve_uploaded_config_for_row(
    change: DiffChange | DiffInformationalChange,
    *,
    uploaded_payload: dict[str, object],
    prefer_name_matching: bool,
) -> tuple[dict[str, object] | None, str | None]:
    if change.target_type == "overwrite":
        return _resolve_uploaded_overwrite_payload(
            change,
            uploaded_payload=uploaded_payload,
            prefer_name_matching=prefer_name_matching,
        )

    uploaded_item = _resolve_uploaded_entity_payload(
        change,
        uploaded_payload=uploaded_payload,
        target_type=change.target_type,
        target_id=change.target_id,
        prefer_name_matching=prefer_name_matching,
    )
    if uploaded_item is None:
        return None, None

    return _filtered_uploaded_payload_for_row(change, uploaded_item), _uploaded_name(
        uploaded_item
    )


def _resolve_uploaded_overwrite_payload(
    change: DiffChange | DiffInformationalChange,
    *,
    uploaded_payload: dict[str, object],
    prefer_name_matching: bool,
) -> tuple[dict[str, object] | None, str | None]:
    parsed = _parse_overwrite_target_id(change.target_id)
    if parsed is None:
        return None, None

    owner_type, owner_id, target_type, target_id = parsed
    owner_item = _resolve_uploaded_entity_payload(
        change,
        uploaded_payload=uploaded_payload,
        target_type=owner_type,
        target_id=owner_id,
        prefer_name_matching=prefer_name_matching,
    )
    if owner_item is None:
        return None, None

    raw_overwrites = owner_item.get("overwrites")
    if not isinstance(raw_overwrites, list):
        return None, _uploaded_name(owner_item)

    for raw_overwrite in cast(list[object], raw_overwrites):
        if not isinstance(raw_overwrite, dict):
            continue
        overwrite = cast(dict[str, object], raw_overwrite)
        target = overwrite.get("target")
        if not isinstance(target, dict):
            continue
        target_payload = cast(dict[str, object], target)
        if (
            target_payload.get("type") != target_type
            or target_payload.get("id") != target_id
        ):
            continue

        payload: dict[str, object] = {}
        allow = _sorted_str_list(overwrite.get("allow"))
        deny = _sorted_str_list(overwrite.get("deny"))
        if allow is not None:
            payload["allow"] = allow
        if deny is not None:
            payload["deny"] = deny
        if payload:
            return payload, _uploaded_name(owner_item)
        return None, _uploaded_name(owner_item)
    return None, _uploaded_name(owner_item)


def _resolve_uploaded_entity_payload(
    change: DiffChange | DiffInformationalChange,
    *,
    uploaded_payload: dict[str, object],
    target_type: str,
    target_id: str | None,
    prefer_name_matching: bool,
) -> dict[str, object] | None:
    section = _section_for_target_type(target_type)
    if section is None:
        return None
    raw_items = uploaded_payload.get(section)
    if not isinstance(raw_items, list):
        return None

    names = _row_name_candidates(change)
    expected_channel_type = (
        _expected_channel_type(change) if target_type == "channel" else None
    )
    expected_parent_scope = (
        _expected_parent_scope(change) if target_type == "channel" else None
    )
    return _find_uploaded_entity_payload(
        cast(list[object], raw_items),
        names=names,
        target_id=target_id,
        target_type=target_type,
        expected_channel_type=expected_channel_type,
        expected_parent_scope=expected_parent_scope,
        prefer_name_matching=prefer_name_matching,
    )


def _section_for_target_type(target_type: str) -> str | None:
    if target_type == "role":
        return "roles"
    if target_type == "category":
        return "categories"
    if target_type == "channel":
        return "channels"
    return None


def _find_uploaded_entity_payload(
    raw_items: list[object],
    *,
    names: list[str],
    target_id: str | None,
    target_type: str,
    expected_channel_type: str | None,
    expected_parent_scope: str | None,
    prefer_name_matching: bool,
) -> dict[str, object] | None:
    best_item: dict[str, object] | None = None
    best_score = -1

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, object], raw_item)

        score = 0
        if not prefer_name_matching and target_id:
            item_id = item.get("id")
            if item_id == target_id:
                score += 100
            elif isinstance(item_id, str) and item_id:
                continue

        item_name = _uploaded_name(item)
        if names and item_name in names:
            score += 50
        elif prefer_name_matching and names:
            continue

        if target_type == "channel":
            if expected_channel_type is not None:
                item_type = item.get("type")
                if isinstance(item_type, str) and item_type != expected_channel_type:
                    continue
                if item_type == expected_channel_type:
                    score += 10
            if expected_parent_scope is not None:
                item_parent_scope = _uploaded_channel_parent_scope(item)
                if (
                    item_parent_scope is not None
                    and item_parent_scope != expected_parent_scope
                ):
                    continue
                if item_parent_scope == expected_parent_scope:
                    score += 10

        if score > best_score:
            best_item = item
            best_score = score

    if best_score <= 0:
        return None
    return deepcopy(best_item)


def _filtered_uploaded_payload_for_row(
    change: DiffChange | DiffInformationalChange,
    uploaded_item: dict[str, object],
) -> dict[str, object] | None:
    candidate_keys: set[str] = set()
    for payload in (change.before, change.after):
        if payload is None:
            continue
        candidate_keys.update(payload.keys())

    filtered: dict[str, object] = {}
    for key in candidate_keys:
        if key not in uploaded_item:
            continue
        value = uploaded_item.get(key)
        if value is None:
            filtered[key] = None
            continue
        if key in {"permissions", "allow", "deny"}:
            sorted_values = _sorted_str_list(value)
            if sorted_values is not None:
                filtered[key] = sorted_values
                continue
        filtered[key] = deepcopy(value)

    if not filtered:
        return None
    return filtered


def _row_name_candidates(change: DiffChange | DiffInformationalChange) -> list[str]:
    names: list[str] = []
    for candidate in (
        change.after_name,
        change.before_name,
        _name_from_payload(change.after),
        _name_from_payload(change.before),
    ):
        if not isinstance(candidate, str) or not candidate:
            continue
        if candidate in names:
            continue
        names.append(candidate)
    return names


def _name_from_payload(payload: dict[str, object] | None) -> str | None:
    if payload is None:
        return None
    raw = payload.get("name")
    if not isinstance(raw, str) or not raw:
        return None
    return raw


def _uploaded_name(payload: dict[str, object]) -> str | None:
    raw = payload.get("name")
    if not isinstance(raw, str) or not raw:
        return None
    return raw


def _expected_channel_type(
    change: DiffChange | DiffInformationalChange,
) -> str | None:
    for payload in (change.after, change.before):
        if payload is None:
            continue
        raw_type = payload.get("type")
        if isinstance(raw_type, str) and raw_type:
            return raw_type
    return None


def _expected_parent_scope(
    change: DiffChange | DiffInformationalChange,
) -> str | None:
    for payload in (change.after, change.before):
        if payload is None:
            continue
        raw_parent = payload.get("parent")
        if isinstance(raw_parent, str) and raw_parent:
            return raw_parent
        raw_parent_name = payload.get("parent_name")
        if isinstance(raw_parent_name, str) and raw_parent_name:
            return raw_parent_name
        raw_parent_id = payload.get("parent_id")
        if isinstance(raw_parent_id, str) and raw_parent_id:
            return raw_parent_id
    return None


def _uploaded_channel_parent_scope(payload: dict[str, object]) -> str | None:
    parent_name = payload.get("parent_name")
    if isinstance(parent_name, str) and parent_name:
        return parent_name
    parent_id = payload.get("parent_id")
    if isinstance(parent_id, str) and parent_id:
        return parent_id
    return None


def _parse_overwrite_target_id(
    target_id: str | None,
) -> tuple[str, str | None, str, str] | None:
    if target_id is None:
        return None
    parts = target_id.split(":")
    if len(parts) != 4:
        return None
    owner_type, owner_id_raw, overwrite_target_type, overwrite_target_id = parts
    if owner_type not in {"category", "channel"}:
        return None
    if overwrite_target_type not in {"role", "member"}:
        return None
    owner_id = owner_id_raw if owner_id_raw and owner_id_raw != "None" else None
    if not overwrite_target_id:
        return None
    return owner_type, owner_id, overwrite_target_type, overwrite_target_id


def _sorted_str_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return sorted(str(item) for item in cast(list[object], value))


__all__ = ["SchemaCommandService", "build_result_markdown_filename"]
