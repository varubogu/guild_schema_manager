from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    discord_token: str
    application_id: int
    log_level: str = "INFO"
    confirm_ttl_seconds: int = 600
    schema_hint_url_template: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN")
        app_id = os.getenv("APPLICATION_ID")
        if not token:
            raise ValueError("DISCORD_TOKEN is required")
        if not app_id:
            raise ValueError("APPLICATION_ID is required")

        schema_hint_url_template = _normalize_optional_str(
            os.getenv("SCHEMA_HINT_URL_TEMPLATE")
        )

        return cls(
            discord_token=token,
            application_id=int(app_id),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            confirm_ttl_seconds=int(os.getenv("CONFIRM_TTL_SECONDS", "600")),
            schema_hint_url_template=schema_hint_url_template,
        )


def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
