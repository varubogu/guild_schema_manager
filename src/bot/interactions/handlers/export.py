from __future__ import annotations

import io
import logging

import discord

from bot.interactions.context import interaction_locale
from bot.localization import t
from bot.usecases.schema import ExportFieldSelection, SchemaCommandService
from bot.usecases.security import AuthorizationError

from .types import GuildSnapshotBuilder, MemberAdminGuard

logger = logging.getLogger(__name__)


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
        fp=io.BytesIO(response.file.content),
        filename=response.file.filename,
    )
    await interaction.followup.send(response.markdown, file=file_obj, ephemeral=True)


__all__ = ["handle_export"]
