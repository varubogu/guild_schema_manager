from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import discord

from bot.localization import SupportedLocale
from bot.usecases.schema_model.models import GuildSchema

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


__all__ = [
    "GuildIdOverrideConfirmer",
    "GuildSnapshotBuilder",
    "MemberAdminGuard",
]
