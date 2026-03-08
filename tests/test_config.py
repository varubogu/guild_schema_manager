from __future__ import annotations

import pytest

from bot.config import Settings


def test_settings_reads_optional_schema_hint_url_template_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("APPLICATION_ID", "123")
    monkeypatch.setenv(
        "SCHEMA_HINT_URL_TEMPLATE",
        "https://example.com/schema/v{version}/schema.json",
    )

    settings = Settings.from_env()

    assert (
        settings.schema_hint_url_template
        == "https://example.com/schema/v{version}/schema.json"
    )


def test_settings_normalizes_blank_schema_hint_url_template_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("APPLICATION_ID", "123")
    monkeypatch.setenv("SCHEMA_HINT_URL_TEMPLATE", "   ")

    settings = Settings.from_env()

    assert settings.schema_hint_url_template is None
