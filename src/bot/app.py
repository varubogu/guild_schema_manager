from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.commands import SchemaCommandService
from bot.commands.cogs import EventsCog, SchemaCog
from bot.commands.context import export_command_context, file_command_context
from bot.commands.handlers import (
    handle_apply,
    handle_diff,
    handle_export,
    maybe_confirm_guild_id_override,
)
from bot.commands.translator import LOCALIZATION_KEY, SchemaCommandTranslator
from bot.config import Settings
from bot.executor.noop import NoopExecutor
from bot.localization import SupportedLocale
from bot.logging_utils import log_async_lifecycle
from bot.security import member_is_guild_admin
from bot.session_store import InMemorySessionStore
from bot.snapshot import build_snapshot_from_guild

logger = logging.getLogger(__name__)


class SchemaBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            application_id=settings.application_id,
        )
        self.settings = settings

        session_store = InMemorySessionStore(ttl_seconds=settings.confirm_ttl_seconds)
        self.service = SchemaCommandService(
            session_store=session_store,
            executor_factory=NoopExecutor,
            schema_hint_url_template=settings.schema_hint_url_template,
        )

    @log_async_lifecycle(logger, "event.setup_hook")
    async def setup_hook(self) -> None:  # type: ignore[override]
        await self.tree.set_translator(SchemaCommandTranslator())
        await self.add_cog(SchemaCog(self))
        await self.add_cog(EventsCog(self))
        await self.tree.sync()

    async def _maybe_confirm_guild_id_override(
        self,
        interaction: discord.Interaction,
        *,
        uploaded: bytes,
        command_name: str,
        locale: SupportedLocale,
    ) -> bytes | None:
        confirm_ttl_seconds = getattr(
            getattr(self, "settings", None),
            "confirm_ttl_seconds",
            600,
        )
        return await maybe_confirm_guild_id_override(
            interaction,
            uploaded=uploaded,
            command_name=command_name,
            locale=locale,
            confirm_ttl_seconds=confirm_ttl_seconds,
        )

    @log_async_lifecycle(
        logger,
        "command.schema.export",
        export_command_context,
    )
    async def handle_export(
        self,
        interaction: discord.Interaction,
        include_name: bool,
        include_permissions: bool,
        include_role_overwrites: bool,
        include_other_settings: bool,
    ) -> None:
        await handle_export(
            service=self.service,
            interaction=interaction,
            include_name=include_name,
            include_permissions=include_permissions,
            include_role_overwrites=include_role_overwrites,
            include_other_settings=include_other_settings,
            member_is_guild_admin=member_is_guild_admin,
            build_snapshot_from_guild=build_snapshot_from_guild,
        )

    @log_async_lifecycle(
        logger,
        "command.schema.diff",
        file_command_context,
    )
    async def handle_diff(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        file_trust_mode: bool,
    ) -> None:
        await handle_diff(
            service=self.service,
            interaction=interaction,
            file=file,
            file_trust_mode=file_trust_mode,
            member_is_guild_admin=member_is_guild_admin,
            build_snapshot_from_guild=build_snapshot_from_guild,
            confirm_guild_id_override=self._maybe_confirm_guild_id_override,
        )

    @log_async_lifecycle(
        logger,
        "command.schema.apply",
        file_command_context,
    )
    async def handle_apply(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        file_trust_mode: bool,
    ) -> None:
        confirm_ttl_seconds = getattr(
            getattr(self, "settings", None),
            "confirm_ttl_seconds",
            600,
        )
        await handle_apply(
            service=self.service,
            interaction=interaction,
            file=file,
            file_trust_mode=file_trust_mode,
            member_is_guild_admin=member_is_guild_admin,
            build_snapshot_from_guild=build_snapshot_from_guild,
            confirm_guild_id_override=self._maybe_confirm_guild_id_override,
            confirm_ttl_seconds=confirm_ttl_seconds,
        )

    async def _handle_export(
        self,
        interaction: discord.Interaction,
        include_name: bool,
        include_permissions: bool,
        include_role_overwrites: bool,
        include_other_settings: bool,
    ) -> None:
        await SchemaBot.handle_export(
            self,
            interaction,
            include_name=include_name,
            include_permissions=include_permissions,
            include_role_overwrites=include_role_overwrites,
            include_other_settings=include_other_settings,
        )

    async def _handle_diff(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        file_trust_mode: bool,
    ) -> None:
        await SchemaBot.handle_diff(
            self,
            interaction,
            file,
            file_trust_mode=file_trust_mode,
        )

    async def _handle_apply(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        file_trust_mode: bool,
    ) -> None:
        await SchemaBot.handle_apply(
            self,
            interaction,
            file,
            file_trust_mode=file_trust_mode,
        )


def create_client(settings: Settings) -> SchemaBot:
    return SchemaBot(settings=settings)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


__all__ = [
    "LOCALIZATION_KEY",
    "SchemaBot",
    "SchemaCommandTranslator",
    "configure_logging",
    "create_client",
]
