from __future__ import annotations

from bot.app import configure_logging, create_client
from bot.config import Settings


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    client = create_client(settings)
    client.run(settings.discord_token)


if __name__ == "__main__":
    main()
