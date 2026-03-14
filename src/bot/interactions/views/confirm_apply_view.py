from __future__ import annotations

import io
import logging

import discord

from bot.interactions.context import confirm_context, interaction_locale
from bot.interactions.responders import content_or_file_notice, markdown_file
from bot.localization import SupportedLocale, t
from bot.logging_utils import log_async_lifecycle
from bot.usecases.executor.discord_executor import DiscordGuildExecutor
from bot.usecases.schema import SchemaCommandService, build_result_markdown_filename
from bot.usecases.snapshot import build_snapshot_from_guild

logger = logging.getLogger(__name__)


class ConfirmApplyView(discord.ui.View):
    def __init__(
        self,
        service: SchemaCommandService,
        token: str,
        *,
        timeout: float,
        locale: SupportedLocale,
    ) -> None:
        super().__init__(timeout=timeout)
        self._service = service
        self._token = token
        self._locale: SupportedLocale = locale

        button = discord.ui.Button[ConfirmApplyView](
            label=t("ui.button.confirm_apply", locale),
            style=discord.ButtonStyle.danger,
        )

        async def on_confirm(interaction: discord.Interaction) -> None:
            await self.confirm(interaction, button)

        button.callback = on_confirm
        self.add_item(button)

    @log_async_lifecycle(
        logger,
        "command.schema.apply.confirm",
        confirm_context,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[ConfirmApplyView],
    ) -> None:
        _ = button
        locale = interaction_locale(interaction)
        if interaction.guild is None:
            logger.warning(
                "command.schema.apply.confirm rejected reason=guild_required"
            )
            await interaction.response.send_message(
                t("ui.error.guild_required", locale),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = await self._service.confirm_apply_async(
                self._token,
                invoker_id=interaction.user.id,
                current=snapshot,
                executor=DiscordGuildExecutor(interaction.guild),
                locale=locale,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "command.schema.apply.confirm failed guild_id=%s user_id=%s",
                interaction.guild.id,
                interaction.user.id,
            )
            await interaction.followup.send(
                t("ui.error.apply_unexpected", locale),
                ephemeral=True,
            )
            return

        files: list[discord.File] = []
        if response.backup_file is not None:
            files.append(
                discord.File(
                    fp=io.BytesIO(response.backup_file.content),
                    filename=response.backup_file.filename,
                )
            )
        files.append(
            markdown_file(
                response.markdown,
                build_result_markdown_filename(snapshot, suffix="apply"),
            )
        )

        await interaction.followup.send(
            content_or_file_notice(response.markdown, locale),
            files=files,
            ephemeral=True,
        )

        if response.report is not None and response.report.failed:
            logger.error(
                "command.schema.apply.confirm operations_failed count=%d guild_id=%s user_id=%s",
                len(response.report.failed),
                interaction.guild.id,
                interaction.user.id,
            )
        if response.report is not None and response.report.skipped:
            logger.warning(
                "command.schema.apply.confirm operations_skipped count=%d guild_id=%s user_id=%s",
                len(response.report.skipped),
                interaction.guild.id,
                interaction.user.id,
            )


__all__ = ["ConfirmApplyView"]
