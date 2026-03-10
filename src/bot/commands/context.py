from __future__ import annotations

from typing import Any

import discord

from bot.localization import SupportedLocale, resolve_user_locale


def interaction_locale(interaction: discord.Interaction) -> SupportedLocale:
    return resolve_user_locale(getattr(interaction, "locale", None))


def interaction_context(interaction: discord.Interaction) -> dict[str, object]:
    command = getattr(getattr(interaction, "command", None), "qualified_name", None)
    return {
        "command": command,
        "guild_id": getattr(interaction.guild, "id", None),
        "user_id": getattr(interaction.user, "id", None),
    }


def confirm_context(
    self: Any,
    interaction: discord.Interaction,
    button: discord.ui.Button[Any],
) -> dict[str, object]:
    _ = self
    _ = button
    return interaction_context(interaction)


def export_command_context(
    self: Any,
    interaction: discord.Interaction,
    include_name: bool,
    include_permissions: bool,
    include_role_overwrites: bool,
    include_other_settings: bool,
) -> dict[str, object]:
    _ = self
    return {
        **interaction_context(interaction),
        "include_name": include_name,
        "include_permissions": include_permissions,
        "include_role_overwrites": include_role_overwrites,
        "include_other_settings": include_other_settings,
    }


def file_command_context(
    self: Any,
    interaction: discord.Interaction,
    file: discord.Attachment,
    file_trust_mode: bool,
) -> dict[str, object]:
    _ = self
    return {
        **interaction_context(interaction),
        "filename": file.filename,
        "file_trust_mode": file_trust_mode,
    }
