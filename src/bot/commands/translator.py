from __future__ import annotations

import discord
from discord import app_commands

from bot.localization import resolve_user_locale, t

LOCALIZATION_KEY = "key"


def localized(key: str) -> app_commands.locale_str:
    return app_commands.locale_str(t(key, "en"), key=key)


GROUP_DESCRIPTION = localized("schema.group.description")
EXPORT_DESCRIPTION = localized("schema.command.export.description")
DIFF_DESCRIPTION = localized("schema.command.diff.description")
APPLY_DESCRIPTION = localized("schema.command.apply.description")
SCHEMA_FILE_DESCRIPTION = localized("schema.argument.file.description")
FILE_TRUST_MODE_DESCRIPTION = localized("schema.argument.file_trust_mode.description")
EXPORT_INCLUDE_NAME_DESCRIPTION = localized(
    "schema.argument.export.include_name.description"
)
EXPORT_INCLUDE_PERMISSIONS_DESCRIPTION = localized(
    "schema.argument.export.include_permissions.description"
)
EXPORT_INCLUDE_ROLE_OVERWRITES_DESCRIPTION = localized(
    "schema.argument.export.include_role_overwrites.description"
)
EXPORT_INCLUDE_OTHER_SETTINGS_DESCRIPTION = localized(
    "schema.argument.export.include_other_settings.description"
)


class SchemaCommandTranslator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None:
        _ = context
        key = string.extras.get(LOCALIZATION_KEY)
        if not isinstance(key, str):
            return None

        locale_code = resolve_user_locale(locale)
        if locale_code != "ja":
            return None

        translated = t(key, locale_code)
        if translated == key:
            return None
        return translated


__all__ = [
    "APPLY_DESCRIPTION",
    "DIFF_DESCRIPTION",
    "EXPORT_DESCRIPTION",
    "EXPORT_INCLUDE_NAME_DESCRIPTION",
    "EXPORT_INCLUDE_OTHER_SETTINGS_DESCRIPTION",
    "EXPORT_INCLUDE_PERMISSIONS_DESCRIPTION",
    "EXPORT_INCLUDE_ROLE_OVERWRITES_DESCRIPTION",
    "FILE_TRUST_MODE_DESCRIPTION",
    "GROUP_DESCRIPTION",
    "LOCALIZATION_KEY",
    "SCHEMA_FILE_DESCRIPTION",
    "SchemaCommandTranslator",
]
