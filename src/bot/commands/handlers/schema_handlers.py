from __future__ import annotations

import io
import logging
from collections.abc import Callable
from typing import Protocol

import discord

from bot.commands.context import interaction_locale
from bot.commands.responders import content_or_file_notice, markdown_file
from bot.commands.views import ConfirmApplyView, GuildIdOverrideView
from bot.localization import SupportedLocale, t
from bot.security import AuthorizationError
from bot.schema.models import GuildSchema
from bot.usecases.schema import (
    ExportFieldSelection,
    SchemaCommandService,
    build_result_markdown_filename,
    extract_uploaded_guild_id,
    overwrite_uploaded_guild_id,
)

logger = logging.getLogger(__name__)

GuildSnapshotBuilder = Callable[[discord.Guild], GuildSchema]
MemberAdminGuard = Callable[[object], bool]


class GuildIdOverrideConfirmer(Protocol):
    async def __call__(
        self,
        interaction: discord.Interaction,
        *,
        uploaded: bytes,
        command_name: str,
        locale: SupportedLocale,
    ) -> bytes | None: ...


async def maybe_confirm_guild_id_override(
    interaction: discord.Interaction,
    *,
    uploaded: bytes,
    command_name: str,
    locale: SupportedLocale,
    confirm_ttl_seconds: int,
) -> bytes | None:
    if interaction.guild is None:
        return None
    uploaded_guild_id = extract_uploaded_guild_id(uploaded)
    if uploaded_guild_id is None:
        return uploaded

    current_guild_id = str(interaction.guild.id)
    if uploaded_guild_id == current_guild_id:
        return uploaded

    logger.warning(
        "%s guild_id_mismatch uploaded=%s current=%s user_id=%s",
        command_name,
        uploaded_guild_id,
        current_guild_id,
        interaction.user.id,
    )
    view = GuildIdOverrideView(
        invoker_id=interaction.user.id,
        timeout=float(confirm_ttl_seconds),
        locale=locale,
    )
    await interaction.followup.send(
        t(
            "ui.guild_id_override.prompt",
            locale,
            uploaded_guild_id=uploaded_guild_id,
            current_guild_id=current_guild_id,
        ),
        view=view,
        ephemeral=True,
    )

    timed_out = await view.wait()
    if timed_out or view.decision is None:
        await interaction.followup.send(
            t("ui.guild_id_override.timed_out", locale),
            ephemeral=True,
        )
        return None
    if not view.decision:
        return None
    return overwrite_uploaded_guild_id(uploaded, current_guild_id)


async def handle_export(
    *,
    service: SchemaCommandService,
    interaction: discord.Interaction,
    include_name: bool,
    include_permissions: bool,
    include_role_overwrites: bool,
    include_other_settings: bool,
    member_is_guild_admin: MemberAdminGuard,
    build_snapshot_from_guild: GuildSnapshotBuilder,
) -> None:
    locale = interaction_locale(interaction)
    if interaction.guild is None:
        logger.warning("command.schema.export rejected reason=guild_required")
        await interaction.response.send_message(
            t("ui.error.guild_required", locale),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    is_admin = member_is_guild_admin(interaction.user)
    try:
        snapshot = build_snapshot_from_guild(interaction.guild)
        response = service.export_schema(
            snapshot,
            invoker_is_admin=is_admin,
            fields=ExportFieldSelection(
                include_name=include_name,
                include_permissions=include_permissions,
                include_role_overwrites=include_role_overwrites,
                include_other_settings=include_other_settings,
            ),
            locale=locale,
        )
    except AuthorizationError as exc:
        logger.warning(
            "command.schema.export authorization_failed guild_id=%s user_id=%s error=%s",
            interaction.guild.id,
            interaction.user.id,
            exc,
        )
        await interaction.followup.send(str(exc), ephemeral=True)
        return

    file_obj = discord.File(
        fp=io.BytesIO(response.file.content), filename=response.file.filename
    )
    await interaction.followup.send(response.markdown, file=file_obj, ephemeral=True)


async def handle_diff(
    *,
    service: SchemaCommandService,
    interaction: discord.Interaction,
    file: discord.Attachment,
    file_trust_mode: bool,
    member_is_guild_admin: MemberAdminGuard,
    build_snapshot_from_guild: GuildSnapshotBuilder,
    confirm_guild_id_override: GuildIdOverrideConfirmer,
) -> None:
    locale = interaction_locale(interaction)
    if interaction.guild is None:
        logger.warning("command.schema.diff rejected reason=guild_required")
        await interaction.response.send_message(
            t("ui.error.guild_required", locale),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    is_admin = member_is_guild_admin(interaction.user)
    try:
        uploaded = await file.read()
        uploaded_guild_id = extract_uploaded_guild_id(uploaded)
        prefer_name_matching = (
            uploaded_guild_id is not None
            and uploaded_guild_id != str(interaction.guild.id)
        )
        uploaded = await confirm_guild_id_override(
            interaction,
            uploaded=uploaded,
            command_name="command.schema.diff",
            locale=locale,
        )
        if uploaded is None:
            return

        snapshot = build_snapshot_from_guild(interaction.guild)
        response = service.diff_schema(
            snapshot,
            uploaded,
            invoker_is_admin=is_admin,
            file_trust_mode=file_trust_mode,
            prefer_name_matching=prefer_name_matching,
            locale=locale,
        )
    except AuthorizationError as exc:
        logger.warning(
            "command.schema.diff authorization_failed guild_id=%s user_id=%s error=%s",
            interaction.guild.id,
            interaction.user.id,
            exc,
        )
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "command.schema.diff validation_failed guild_id=%s user_id=%s filename=%s",
            interaction.guild.id,
            interaction.user.id,
            file.filename,
        )
        await interaction.followup.send(
            t("ui.error.validation", locale, error=str(exc)),
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        content_or_file_notice(response.markdown, locale),
        file=markdown_file(
            response.markdown,
            build_result_markdown_filename(snapshot, suffix="diff"),
        ),
        ephemeral=True,
    )


async def handle_apply(
    *,
    service: SchemaCommandService,
    interaction: discord.Interaction,
    file: discord.Attachment,
    file_trust_mode: bool,
    member_is_guild_admin: MemberAdminGuard,
    build_snapshot_from_guild: GuildSnapshotBuilder,
    confirm_guild_id_override: GuildIdOverrideConfirmer,
    confirm_ttl_seconds: int,
) -> None:
    locale = interaction_locale(interaction)
    if interaction.guild is None:
        logger.warning("command.schema.apply rejected reason=guild_required")
        await interaction.response.send_message(
            t("ui.error.guild_required", locale),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    is_admin = member_is_guild_admin(interaction.user)
    try:
        uploaded = await file.read()
        uploaded_guild_id = extract_uploaded_guild_id(uploaded)
        prefer_name_matching = (
            uploaded_guild_id is not None
            and uploaded_guild_id != str(interaction.guild.id)
        )
        uploaded = await confirm_guild_id_override(
            interaction,
            uploaded=uploaded,
            command_name="command.schema.apply",
            locale=locale,
        )
        if uploaded is None:
            return
        snapshot = build_snapshot_from_guild(interaction.guild)
        response = service.apply_schema_preview(
            snapshot,
            uploaded,
            invoker_is_admin=is_admin,
            invoker_id=interaction.user.id,
            file_trust_mode=file_trust_mode,
            prefer_name_matching=prefer_name_matching,
            locale=locale,
        )
    except AuthorizationError as exc:
        logger.warning(
            "command.schema.apply authorization_failed guild_id=%s user_id=%s error=%s",
            interaction.guild.id,
            interaction.user.id,
            exc,
        )
        await interaction.followup.send(str(exc), ephemeral=True)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "command.schema.apply validation_failed guild_id=%s user_id=%s filename=%s",
            interaction.guild.id,
            interaction.user.id,
            file.filename,
        )
        await interaction.followup.send(
            t("ui.error.validation", locale, error=str(exc)),
            ephemeral=True,
        )
        return

    if response.confirmation_token is None:
        await interaction.followup.send(
            content_or_file_notice(response.markdown, locale),
            file=markdown_file(
                response.markdown,
                build_result_markdown_filename(snapshot, suffix="apply"),
            ),
            ephemeral=True,
        )
        return

    view = ConfirmApplyView(
        service,
        response.confirmation_token,
        timeout=float(confirm_ttl_seconds),
        locale=locale,
    )
    await interaction.followup.send(
        content_or_file_notice(response.markdown, locale),
        file=markdown_file(
            response.markdown,
            build_result_markdown_filename(snapshot, suffix="apply"),
        ),
        view=view,
        ephemeral=True,
    )


__all__ = [
    "handle_apply",
    "handle_diff",
    "handle_export",
    "maybe_confirm_guild_id_override",
]
