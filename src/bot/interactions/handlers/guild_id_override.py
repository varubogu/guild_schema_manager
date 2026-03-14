from __future__ import annotations

import logging

import discord

from bot.interactions.views import GuildIdOverrideView
from bot.localization import SupportedLocale, t
from bot.usecases.schema import extract_uploaded_guild_id, overwrite_uploaded_guild_id

logger = logging.getLogger(__name__)


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


__all__ = ["maybe_confirm_guild_id_override"]
