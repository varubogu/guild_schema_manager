from __future__ import annotations

import discord

from bot.interactions.context import interaction_locale
from bot.localization import SupportedLocale, t


class GuildIdOverrideView(discord.ui.View):
    def __init__(
        self,
        *,
        invoker_id: int,
        timeout: float,
        locale: SupportedLocale,
    ) -> None:
        super().__init__(timeout=timeout)
        self._invoker_id = invoker_id
        self._locale: SupportedLocale = locale
        self.decision: bool | None = None

        approve_button = discord.ui.Button[GuildIdOverrideView](
            label=t("ui.button.guild_id_override.approve", locale),
            style=discord.ButtonStyle.success,
        )
        cancel_button = discord.ui.Button[GuildIdOverrideView](
            label=t("ui.button.cancel", locale),
            style=discord.ButtonStyle.secondary,
        )

        async def on_approve(interaction: discord.Interaction) -> None:
            await self.approve(interaction, approve_button)

        async def on_cancel(interaction: discord.Interaction) -> None:
            await self.cancel(interaction, cancel_button)

        approve_button.callback = on_approve
        cancel_button.callback = on_cancel
        self.add_item(approve_button)
        self.add_item(cancel_button)

    async def _reject_non_invoker(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self._invoker_id:
            return False
        response_locale = interaction_locale(interaction)
        await interaction.response.send_message(
            t("ui.error.invoker_only_confirmation_response", response_locale),
            ephemeral=True,
        )
        return True

    async def approve(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[GuildIdOverrideView],
    ) -> None:
        _ = button
        if await self._reject_non_invoker(interaction):
            return
        self.decision = True
        await interaction.response.edit_message(
            content=t("ui.guild_id_override.approved", self._locale),
            view=None,
        )
        self.stop()

    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[GuildIdOverrideView],
    ) -> None:
        _ = button
        if await self._reject_non_invoker(interaction):
            return
        self.decision = False
        await interaction.response.edit_message(
            content=t("ui.guild_id_override.canceled", self._locale),
            view=None,
        )
        self.stop()


__all__ = ["GuildIdOverrideView"]
