from __future__ import annotations

import logging

from discord.ext import commands

from bot.logging_utils import log_async_lifecycle

logger = logging.getLogger(__name__)


class OnReadyEventCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    @log_async_lifecycle(logger, "event.on_ready")
    async def on_ready(self) -> None:
        logger.info(
            "bot.ready guild_count=%d user_id=%s",
            len(self.bot.guilds),
            getattr(self.bot.user, "id", None),
        )


__all__ = ["OnReadyEventCog"]
