from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from bot.diff import DiffValidationError, diff_schemas
from bot.executor import AsyncOperationExecutor, OperationExecutor, execute_plan, execute_plan_async
from bot.planner import ApplyReport, build_apply_plan
from bot.rendering import render_apply_report, render_diff_markdown
from bot.schema.errors import SchemaValidationError
from bot.schema.models import GuildSchema
from bot.schema.parser import parse_schema_yaml, schema_to_yaml
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
    ) -> None:
        self._session_store = session_store
        self._executor_factory = executor_factory

    def export_schema(self, current: GuildSchema, *, invoker_is_admin: bool) -> ExportResponse:
        require_guild_admin(invoker_is_admin)
        yaml_text = schema_to_yaml(current)
        summary = (
            f"Exported roles={len(current.roles)}, categories={len(current.categories)}, "
            f"channels={len(current.channels)}"
        )
        return ExportResponse(
            markdown=summary,
            file=FilePayload(filename="guild-schema.yaml", content=yaml_text.encode("utf-8")),
        )

    def diff_schema(
        self,
        current: GuildSchema,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
    ) -> DiffResponse:
        require_guild_admin(invoker_is_admin)
        desired = parse_schema_yaml(uploaded)
        result = diff_schemas(current, desired)
        return DiffResponse(markdown=render_diff_markdown(result))

    def apply_schema_preview(
        self,
        current: GuildSchema,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        invoker_id: int,
    ) -> ApplyPreviewResponse:
        require_guild_admin(invoker_is_admin)
        desired = parse_schema_yaml(uploaded)
        diff_result = diff_schemas(current, desired)

        if not diff_result.changes:
            return ApplyPreviewResponse(
                markdown="No changes detected. Nothing to apply.",
                confirmation_token=None,
            )

        plan = build_apply_plan(diff_result)
        pending = self._session_store.create(
            invoker_id=invoker_id,
            desired_schema=desired,
            diff_result=diff_result,
            apply_plan=plan,
        )
        preview = render_diff_markdown(diff_result)
        preview += f"\n\nConfirmation token: `{pending.token}` (valid for 10 minutes)"
        return ApplyPreviewResponse(markdown=preview, confirmation_token=pending.token)

    def confirm_apply(
        self,
        token: str,
        *,
        invoker_id: int,
        current: GuildSchema,
    ) -> ApplyExecutionResponse:
        try:
            pending = self._session_store.consume(token, invoker_id)
        except SessionNotFoundError:
            return ApplyExecutionResponse(
                markdown="Confirmation session not found. Please rerun /schema apply.",
                backup_file=None,
                report=None,
            )
        except SessionExpiredError:
            return ApplyExecutionResponse(
                markdown="Confirmation expired. Please rerun /schema apply.",
                backup_file=None,
                report=None,
            )
        except SessionForbiddenError:
            return ApplyExecutionResponse(
                markdown="Only the original invoker can confirm this apply.",
                backup_file=None,
                report=None,
            )
        except SessionError as exc:
            return ApplyExecutionResponse(markdown=str(exc), backup_file=None, report=None)

        ensure_invoker_only(invoker_id, pending.invoker_id)

        backup = schema_to_yaml(current).encode("utf-8")
        executor = self._executor_factory()
        report = execute_plan(plan=pending.apply_plan, backup_file=backup, executor=executor)
        markdown = render_apply_report(report)
        return ApplyExecutionResponse(
            markdown=markdown,
            backup_file=FilePayload(filename="guild-schema-backup.yaml", content=backup),
            report=report,
        )

    async def confirm_apply_async(
        self,
        token: str,
        *,
        invoker_id: int,
        current: GuildSchema,
        executor: AsyncOperationExecutor,
    ) -> ApplyExecutionResponse:
        try:
            pending = self._session_store.consume(token, invoker_id)
        except SessionNotFoundError:
            return ApplyExecutionResponse(
                markdown="Confirmation session not found. Please rerun /schema apply.",
                backup_file=None,
                report=None,
            )
        except SessionExpiredError:
            return ApplyExecutionResponse(
                markdown="Confirmation expired. Please rerun /schema apply.",
                backup_file=None,
                report=None,
            )
        except SessionForbiddenError:
            return ApplyExecutionResponse(
                markdown="Only the original invoker can confirm this apply.",
                backup_file=None,
                report=None,
            )
        except SessionError as exc:
            return ApplyExecutionResponse(markdown=str(exc), backup_file=None, report=None)

        ensure_invoker_only(invoker_id, pending.invoker_id)

        backup = schema_to_yaml(current).encode("utf-8")
        report = await execute_plan_async(plan=pending.apply_plan, backup_file=backup, executor=executor)
        markdown = render_apply_report(report)
        return ApplyExecutionResponse(
            markdown=markdown,
            backup_file=FilePayload(filename="guild-schema-backup.yaml", content=backup),
            report=report,
        )


def parse_uploaded_schema(uploaded: bytes) -> GuildSchema:
    try:
        return parse_schema_yaml(uploaded)
    except (SchemaValidationError, DiffValidationError) as exc:
        raise ValueError(str(exc)) from exc
