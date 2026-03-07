from __future__ import annotations

import pytest

from bot.config import Settings


def test_settings_reads_optional_schema_repo_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("APPLICATION_ID", "123")
    monkeypatch.setenv("SCHEMA_REPO_OWNER", "example-org")
    monkeypatch.setenv("SCHEMA_REPO_NAME", "guild-schema-manager")

    settings = Settings.from_env()

    assert settings.schema_repo_owner == "example-org"
    assert settings.schema_repo_name == "guild-schema-manager"


def test_settings_normalizes_blank_schema_repo_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "token")
    monkeypatch.setenv("APPLICATION_ID", "123")
    monkeypatch.setenv("SCHEMA_REPO_OWNER", "   ")
    monkeypatch.setenv("SCHEMA_REPO_NAME", "")

    settings = Settings.from_env()

    assert settings.schema_repo_owner is None
    assert settings.schema_repo_name is None
