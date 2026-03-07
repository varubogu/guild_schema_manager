from __future__ import annotations

import io
import logging

import discord
from discord import app_commands

from bot.commands import SchemaCommandService
from bot.config import Settings
from bot.executor.discord_executor import DiscordGuildExecutor
from bot.executor.noop import NoopExecutor
from bot.security import AuthorizationError, member_is_guild_admin
from bot.session_store import InMemorySessionStore
from bot.snapshot import build_snapshot_from_guild


class ConfirmApplyView(discord.ui.View):
    def __init__(
        self,
        service: SchemaCommandService,
        token: str,
        *,
        timeout: float,
    ) -> None:
        super().__init__(timeout=timeout)
        self._service = service
        self._token = token

    @discord.ui.button(label="Confirm Apply", style=discord.ButtonStyle.danger)
    async def confirm(  # type: ignore[override]
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        _ = button
        if interaction.guild is None:
            await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
            return

        snapshot = build_snapshot_from_guild(interaction.guild)
        response = await self._service.confirm_apply_async(
            self._token,
            invoker_id=interaction.user.id,
            current=snapshot,
            executor=DiscordGuildExecutor(interaction.guild),
        )

        files: list[discord.File] = []
        if response.backup_file is not None:
            files.append(
                discord.File(
                    fp=io.BytesIO(response.backup_file.content),
                    filename=response.backup_file.filename,
                )
            )

        if interaction.response.is_done():
            await interaction.followup.send(response.markdown, files=files, ephemeral=True)
        else:
            await interaction.response.send_message(response.markdown, files=files, ephemeral=True)


class SchemaBot(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.settings = settings

        self.tree = app_commands.CommandTree(self)
        session_store = InMemorySessionStore(ttl_seconds=settings.confirm_ttl_seconds)
        self.service = SchemaCommandService(session_store=session_store, executor_factory=NoopExecutor)

    async def setup_hook(self) -> None:
        schema_group = app_commands.Group(name="schema", description="Guild schema operations")

        @schema_group.command(name="export", description="Export guild schema to YAML")
        async def export(interaction: discord.Interaction) -> None:
            await self._handle_export(interaction)

        @schema_group.command(name="diff", description="Diff uploaded YAML against current guild")
        @app_commands.describe(file="Schema YAML file")
        async def diff(interaction: discord.Interaction, file: discord.Attachment) -> None:
            await self._handle_diff(interaction, file)

        @schema_group.command(name="apply", description="Preview and apply uploaded YAML")
        @app_commands.describe(file="Schema YAML file")
        async def apply(interaction: discord.Interaction, file: discord.Attachment) -> None:
            await self._handle_apply(interaction, file)

        self.tree.add_command(schema_group)
        await self.tree.sync()

    async def _handle_export(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
            return

        is_admin = member_is_guild_admin(interaction.user)
        try:
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = self.service.export_schema(snapshot, invoker_is_admin=is_admin)
        except AuthorizationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        file = discord.File(fp=io.BytesIO(response.file.content), filename=response.file.filename)
        await interaction.response.send_message(response.markdown, file=file, ephemeral=True)

    async def _handle_diff(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
            return

        is_admin = member_is_guild_admin(interaction.user)
        try:
            uploaded = await file.read()
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = self.service.diff_schema(snapshot, uploaded, invoker_is_admin=is_admin)
        except AuthorizationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(f"Validation error: {exc}", ephemeral=True)
            return

        await interaction.response.send_message(response.markdown, ephemeral=True)

    async def _handle_apply(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
            return

        is_admin = member_is_guild_admin(interaction.user)
        try:
            uploaded = await file.read()
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = self.service.apply_schema_preview(
                snapshot,
                uploaded,
                invoker_is_admin=is_admin,
                invoker_id=interaction.user.id,
            )
        except AuthorizationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(f"Validation error: {exc}", ephemeral=True)
            return

        if response.confirmation_token is None:
            await interaction.response.send_message(response.markdown, ephemeral=True)
            return

        view = ConfirmApplyView(
            self.service,
            response.confirmation_token,
            timeout=float(self.settings.confirm_ttl_seconds),
        )
        await interaction.response.send_message(response.markdown, view=view, ephemeral=True)


def create_client(settings: Settings) -> SchemaBot:
    return SchemaBot(settings=settings)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
