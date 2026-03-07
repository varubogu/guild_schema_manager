from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    discord_token: str
    application_id: int
    log_level: str = "INFO"
    confirm_ttl_seconds: int = 600

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN")
        app_id = os.getenv("APPLICATION_ID")
        if not token:
            raise ValueError("DISCORD_TOKEN is required")
        if not app_id:
            raise ValueError("APPLICATION_ID is required")

        return cls(
            discord_token=token,
            application_id=int(app_id),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            confirm_ttl_seconds=int(os.getenv("CONFIRM_TTL_SECONDS", "600")),
        )
