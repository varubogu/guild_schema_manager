from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.commands.translator import (
    APPLY_DESCRIPTION,
    DIFF_DESCRIPTION,
    EXPORT_DESCRIPTION,
    EXPORT_INCLUDE_NAME_DESCRIPTION,
    EXPORT_INCLUDE_OTHER_SETTINGS_DESCRIPTION,
    EXPORT_INCLUDE_PERMISSIONS_DESCRIPTION,
    EXPORT_INCLUDE_ROLE_OVERWRITES_DESCRIPTION,
    FILE_TRUST_MODE_DESCRIPTION,
    GROUP_DESCRIPTION,
    SCHEMA_FILE_DESCRIPTION,
)

if TYPE_CHECKING:
    from bot.app import SchemaBot


class SchemaCog(
    commands.GroupCog,
    group_name="schema",
    group_description=GROUP_DESCRIPTION,
):
    def __init__(self, bot: "SchemaBot") -> None:
        super().__init__()
        self._bot = bot

    @app_commands.command(name="export", description=EXPORT_DESCRIPTION)
    @app_commands.describe(
        include_name=EXPORT_INCLUDE_NAME_DESCRIPTION,
        include_permissions=EXPORT_INCLUDE_PERMISSIONS_DESCRIPTION,
        include_role_overwrites=EXPORT_INCLUDE_ROLE_OVERWRITES_DESCRIPTION,
        include_other_settings=EXPORT_INCLUDE_OTHER_SETTINGS_DESCRIPTION,
    )
    async def export(
        self,
        interaction: discord.Interaction,
        include_name: bool = True,
        include_permissions: bool = True,
        include_role_overwrites: bool = True,
        include_other_settings: bool = True,
    ) -> None:
        await self._bot.handle_export(
            interaction,
            include_name=include_name,
            include_permissions=include_permissions,
            include_role_overwrites=include_role_overwrites,
            include_other_settings=include_other_settings,
        )

    @app_commands.command(name="diff", description=DIFF_DESCRIPTION)
    @app_commands.describe(
        file=SCHEMA_FILE_DESCRIPTION,
        file_trust_mode=FILE_TRUST_MODE_DESCRIPTION,
    )
    async def diff(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        file_trust_mode: bool = False,
    ) -> None:
        await self._bot.handle_diff(interaction, file, file_trust_mode=file_trust_mode)

    @app_commands.command(name="apply", description=APPLY_DESCRIPTION)
    @app_commands.describe(
        file=SCHEMA_FILE_DESCRIPTION,
        file_trust_mode=FILE_TRUST_MODE_DESCRIPTION,
    )
    async def apply(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        file_trust_mode: bool = False,
    ) -> None:
        await self._bot.handle_apply(interaction, file, file_trust_mode=file_trust_mode)


__all__ = ["SchemaCog"]
