from __future__ import annotations

import asyncio
from typing import Any, cast

import discord
from discord import app_commands

from bot.app import JA_TRANSLATIONS, LOCALIZATION_KEY, SchemaCommandTranslator


def test_schema_command_translator_returns_japanese_translation() -> None:
    translator = SchemaCommandTranslator()
    key = "schema.command.export.description"
    localized = app_commands.locale_str(
        "Export guild schema to YAML",
        **{LOCALIZATION_KEY: key},
    )

    translated = asyncio.run(
        translator.translate(localized, discord.Locale.japanese, cast(Any, None))
    )

    assert translated == JA_TRANSLATIONS[key]


def test_schema_command_translator_returns_none_for_non_japanese_locale() -> None:
    translator = SchemaCommandTranslator()
    localized = app_commands.locale_str(
        "Export guild schema to YAML",
        **{LOCALIZATION_KEY: "schema.command.export.description"},
    )

    translated = asyncio.run(
        translator.translate(
            localized,
            discord.Locale.american_english,
            cast(Any, None),
        )
    )

    assert translated is None


def test_schema_command_translator_returns_none_for_unknown_key() -> None:
    translator = SchemaCommandTranslator()
    localized = app_commands.locale_str(
        "Unknown text",
        **{LOCALIZATION_KEY: "schema.unknown"},
    )

    translated = asyncio.run(
        translator.translate(localized, discord.Locale.japanese, cast(Any, None))
    )

    assert translated is None
