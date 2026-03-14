from __future__ import annotations

import logging

import discord

from bot.interactions.context import interaction_locale
from bot.interactions.responders import content_or_file_notice, markdown_file
from bot.localization import t
from bot.usecases.schema import (
    SchemaCommandService,
    build_result_markdown_filename,
    extract_uploaded_guild_id,
)
from bot.usecases.security import AuthorizationError

from .types import GuildIdOverrideConfirmer, GuildSnapshotBuilder, MemberAdminGuard

logger = logging.getLogger(__name__)


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


__all__ = ["handle_diff"]
