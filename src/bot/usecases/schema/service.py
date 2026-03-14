from __future__ import annotations

from typing import Callable

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
from bot.usecases.executor import (
    AsyncOperationExecutor,
    OperationExecutor,
    execute_plan,
    execute_plan_async,
)
from bot.usecases.planner import build_apply_plan
from bot.usecases.rendering import render_apply_report, render_diff_markdown
from bot.usecases.schema_model.models import GuildSchema
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

        uploaded_payload = try_load_uploaded_mapping(uploaded)
        desired = (
            parse_schema_yaml(uploaded)
            if file_trust_mode
            else parse_schema_patch_yaml(
                uploaded,
                current,
                prefer_name_matching=prefer_name_matching,
            )
        )

        diff_result = diff_schemas(
            current,
            desired,
            prefer_name_matching=prefer_name_matching,
        )
        diff_result.informational_changes = build_informational_changes(
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


__all__ = ["SchemaCommandService", "build_result_markdown_filename"]
