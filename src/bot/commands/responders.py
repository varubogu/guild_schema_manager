from __future__ import annotations

import io

import discord

from bot.localization import SupportedLocale

INLINE_MESSAGE_MAX_LENGTH = 1800


def content_or_file_notice(markdown: str, locale: SupportedLocale) -> str:
    if len(markdown) <= INLINE_MESSAGE_MAX_LENGTH:
        return markdown
    if locale == "ja":
        return "結果が長いため、添付ファイルを確認してください。"
    return "Result is attached as a file because it is too long to display inline."


def markdown_file(markdown: str, filename: str) -> discord.File:
    return discord.File(
        fp=io.BytesIO(markdown.encode("utf-8")),
        filename=filename,
    )


__all__ = [
    "content_or_file_notice",
    "markdown_file",
]
