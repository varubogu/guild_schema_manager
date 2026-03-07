from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    discord_token: str
    application_id: int
    log_level: str = "INFO"
    confirm_ttl_seconds: int = 600
    schema_repo_owner: str | None = None
    schema_repo_name: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN")
        app_id = os.getenv("APPLICATION_ID")
        if not token:
            raise ValueError("DISCORD_TOKEN is required")
        if not app_id:
            raise ValueError("APPLICATION_ID is required")

        owner = _normalize_optional_str(os.getenv("SCHEMA_REPO_OWNER"))
        repo_name = _normalize_optional_str(os.getenv("SCHEMA_REPO_NAME"))

        return cls(
            discord_token=token,
            application_id=int(app_id),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            confirm_ttl_seconds=int(os.getenv("CONFIRM_TTL_SECONDS", "600")),
            schema_repo_owner=owner,
            schema_repo_name=repo_name,
        )


def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
