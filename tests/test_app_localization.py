from __future__ import annotations

import asyncio
from typing import Any, cast

import discord
from discord import app_commands

from bot.app import LOCALIZATION_KEY, SchemaCommandTranslator
from bot.localization import (
    REQUIRED_MESSAGE_IDS,
    has_message_id,
    resolve_user_locale,
    t,
)


def test_schema_command_translator_returns_japanese_translation() -> None:
    translator = SchemaCommandTranslator()
    key = "schema.command.export.description"
    localized = app_commands.locale_str(
        t(key, "en"),
        **{LOCALIZATION_KEY: key},
    )

    translated = asyncio.run(
        translator.translate(localized, discord.Locale.japanese, cast(Any, None))
    )

    assert translated == t(key, "ja")


def test_schema_command_translator_returns_none_for_non_japanese_locale() -> None:
    translator = SchemaCommandTranslator()
    localized = app_commands.locale_str(
        t("schema.command.export.description", "en"),
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


def test_resolve_user_locale_treats_only_japanese_as_ja() -> None:
    assert resolve_user_locale(discord.Locale.japanese) == "ja"
    assert resolve_user_locale("ja-JP") == "ja"
    assert resolve_user_locale(discord.Locale.american_english) == "en"
    assert resolve_user_locale(discord.Locale.french) == "en"
    assert resolve_user_locale(None) == "en"


def test_catalog_contains_required_ids_for_both_locales() -> None:
    for message_id in REQUIRED_MESSAGE_IDS:
        assert has_message_id(message_id)
        assert t(message_id, "ja") != message_id
        assert t(message_id, "en") != message_id
