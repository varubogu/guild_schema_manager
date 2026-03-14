from __future__ import annotations

from bot.cogs import OnReadyEventCog, SchemaCog
from bot.cogs.commands.schema import SchemaCog as SchemaCogFromModule
from bot.cogs.events.on_ready import OnReadyEventCog as OnReadyEventCogFromModule


def test_public_cog_exports_match_module_classes() -> None:
    assert SchemaCog is SchemaCogFromModule
    assert OnReadyEventCog is OnReadyEventCogFromModule
