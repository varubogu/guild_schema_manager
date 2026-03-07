from __future__ import annotations

import io
import logging

import discord
from discord import app_commands

from bot.commands import SchemaCommandService
from bot.config import Settings
from bot.executor.discord_executor import DiscordGuildExecutor
from bot.executor.noop import NoopExecutor
from bot.logging_utils import log_async_lifecycle
from bot.security import AuthorizationError, member_is_guild_admin
from bot.session_store import InMemorySessionStore
from bot.snapshot import build_snapshot_from_guild

logger = logging.getLogger(__name__)

LOCALIZATION_KEY = "key"


def _localized(message: str, key: str) -> app_commands.locale_str:
    return app_commands.locale_str(message, key=key)


GROUP_DESCRIPTION = _localized(
    "Guild schema operations",
    "schema.group.description",
)
EXPORT_DESCRIPTION = _localized(
    "Export guild schema to YAML",
    "schema.command.export.description",
)
DIFF_DESCRIPTION = _localized(
    "Diff uploaded YAML against current guild",
    "schema.command.diff.description",
)
APPLY_DESCRIPTION = _localized(
    "Preview and apply uploaded YAML",
    "schema.command.apply.description",
)
SCHEMA_FILE_DESCRIPTION = _localized(
    "Schema YAML file",
    "schema.argument.file.description",
)

JA_TRANSLATIONS: dict[str, str] = {
    "schema.group.description": "ギルドスキーマ操作",
    "schema.command.export.description": "ギルド構成をYAML出力",
    "schema.command.diff.description": "アップロードYAMLと現在のギルド構成を比較",
    "schema.command.apply.description": "アップロードYAMLをプレビューして適用",
    "schema.argument.file.description": "スキーマYAMLファイル",
}


class SchemaCommandTranslator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None:
        _ = context
        if locale != discord.Locale.japanese:
            return None

        key = string.extras.get(LOCALIZATION_KEY)
        if not isinstance(key, str):
            return None
        return JA_TRANSLATIONS.get(key)


def _interaction_context(interaction: discord.Interaction) -> dict[str, object]:
    command = getattr(getattr(interaction, "command", None), "qualified_name", None)
    return {
        "command": command,
        "guild_id": getattr(interaction.guild, "id", None),
        "user_id": getattr(interaction.user, "id", None),
    }


def _confirm_context(
    self: "ConfirmApplyView",
    interaction: discord.Interaction,
    button: discord.ui.Button["ConfirmApplyView"],
) -> dict[str, object]:
    _ = self
    _ = button
    return _interaction_context(interaction)


def _command_context(
    self: "SchemaBot",
    interaction: discord.Interaction,
) -> dict[str, object]:
    _ = self
    return _interaction_context(interaction)


def _file_command_context(
    self: "SchemaBot",
    interaction: discord.Interaction,
    file: discord.Attachment,
) -> dict[str, object]:
    _ = self
    return {
        **_interaction_context(interaction),
        "filename": file.filename,
    }


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
    @log_async_lifecycle(
        logger,
        "command.schema.apply.confirm",
        _confirm_context,
    )
    async def confirm(  # type: ignore[override]
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["ConfirmApplyView"],
    ) -> None:
        _ = button
        if interaction.guild is None:
            logger.warning(
                "command.schema.apply.confirm rejected reason=guild_required"
            )
            await interaction.response.send_message(
                "This command must be used in a guild.", ephemeral=True
            )
            return

        try:
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = await self._service.confirm_apply_async(
                self._token,
                invoker_id=interaction.user.id,
                current=snapshot,
                executor=DiscordGuildExecutor(interaction.guild),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "command.schema.apply.confirm failed guild_id=%s user_id=%s",
                interaction.guild.id,
                interaction.user.id,
            )
            message = "Apply execution failed due to an unexpected error."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return

        files: list[discord.File] = []
        if response.backup_file is not None:
            files.append(
                discord.File(
                    fp=io.BytesIO(response.backup_file.content),
                    filename=response.backup_file.filename,
                )
            )

        if interaction.response.is_done():
            await interaction.followup.send(
                response.markdown, files=files, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                response.markdown, files=files, ephemeral=True
            )

        if response.report is not None and response.report.failed:
            logger.error(
                "command.schema.apply.confirm operations_failed count=%d guild_id=%s user_id=%s",
                len(response.report.failed),
                interaction.guild.id,
                interaction.user.id,
            )
        if response.report is not None and response.report.skipped:
            logger.warning(
                "command.schema.apply.confirm operations_skipped count=%d guild_id=%s user_id=%s",
                len(response.report.skipped),
                interaction.guild.id,
                interaction.user.id,
            )


class SchemaBot(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.settings = settings

        self.tree = app_commands.CommandTree(self)
        session_store = InMemorySessionStore(ttl_seconds=settings.confirm_ttl_seconds)
        self.service = SchemaCommandService(
            session_store=session_store,
            executor_factory=NoopExecutor,
            schema_repo_owner=settings.schema_repo_owner,
            schema_repo_name=settings.schema_repo_name,
        )

    @log_async_lifecycle(logger, "event.setup_hook")
    async def setup_hook(self) -> None:  # type: ignore[override]
        await self.tree.set_translator(SchemaCommandTranslator())
        schema_group = app_commands.Group(
            name="schema",
            description=GROUP_DESCRIPTION,
        )

        @schema_group.command(
            name="export",
            description=EXPORT_DESCRIPTION,
        )
        async def export(  # pyright: ignore[reportUnusedFunction]
            interaction: discord.Interaction,
        ) -> None:
            await self._handle_export(interaction)

        @schema_group.command(
            name="diff",
            description=DIFF_DESCRIPTION,
        )
        @app_commands.describe(file=SCHEMA_FILE_DESCRIPTION)
        async def diff(  # pyright: ignore[reportUnusedFunction]
            interaction: discord.Interaction,
            file: discord.Attachment,
        ) -> None:
            await self._handle_diff(interaction, file)

        @schema_group.command(
            name="apply",
            description=APPLY_DESCRIPTION,
        )
        @app_commands.describe(file=SCHEMA_FILE_DESCRIPTION)
        async def apply(  # pyright: ignore[reportUnusedFunction]
            interaction: discord.Interaction,
            file: discord.Attachment,
        ) -> None:
            await self._handle_apply(interaction, file)

        self.tree.add_command(schema_group)
        await self.tree.sync()

    @log_async_lifecycle(logger, "event.on_ready")
    async def on_ready(self) -> None:
        logger.info(
            "bot.ready guild_count=%d user_id=%s",
            len(self.guilds),
            getattr(self.user, "id", None),
        )

    @log_async_lifecycle(
        logger,
        "command.schema.export",
        _command_context,
    )
    async def _handle_export(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            logger.warning("command.schema.export rejected reason=guild_required")
            await interaction.response.send_message(
                "This command must be used in a guild.", ephemeral=True
            )
            return

        is_admin = member_is_guild_admin(interaction.user)
        try:
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = self.service.export_schema(snapshot, invoker_is_admin=is_admin)
        except AuthorizationError as exc:
            logger.warning(
                "command.schema.export authorization_failed guild_id=%s user_id=%s error=%s",
                interaction.guild.id,
                interaction.user.id,
                exc,
            )
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        file = discord.File(
            fp=io.BytesIO(response.file.content), filename=response.file.filename
        )
        await interaction.response.send_message(
            response.markdown, file=file, ephemeral=True
        )

    @log_async_lifecycle(
        logger,
        "command.schema.diff",
        _file_command_context,
    )
    async def _handle_diff(
        self, interaction: discord.Interaction, file: discord.Attachment
    ) -> None:
        if interaction.guild is None:
            logger.warning("command.schema.diff rejected reason=guild_required")
            await interaction.response.send_message(
                "This command must be used in a guild.", ephemeral=True
            )
            return

        is_admin = member_is_guild_admin(interaction.user)
        try:
            uploaded = await file.read()
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = self.service.diff_schema(
                snapshot, uploaded, invoker_is_admin=is_admin
            )
        except AuthorizationError as exc:
            logger.warning(
                "command.schema.diff authorization_failed guild_id=%s user_id=%s error=%s",
                interaction.guild.id,
                interaction.user.id,
                exc,
            )
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "command.schema.diff validation_failed guild_id=%s user_id=%s filename=%s",
                interaction.guild.id,
                interaction.user.id,
                file.filename,
            )
            await interaction.response.send_message(
                f"Validation error: {exc}", ephemeral=True
            )
            return

        await interaction.response.send_message(response.markdown, ephemeral=True)

    @log_async_lifecycle(
        logger,
        "command.schema.apply",
        _file_command_context,
    )
    async def _handle_apply(
        self, interaction: discord.Interaction, file: discord.Attachment
    ) -> None:
        if interaction.guild is None:
            logger.warning("command.schema.apply rejected reason=guild_required")
            await interaction.response.send_message(
                "This command must be used in a guild.", ephemeral=True
            )
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
            logger.warning(
                "command.schema.apply authorization_failed guild_id=%s user_id=%s error=%s",
                interaction.guild.id,
                interaction.user.id,
                exc,
            )
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "command.schema.apply validation_failed guild_id=%s user_id=%s filename=%s",
                interaction.guild.id,
                interaction.user.id,
                file.filename,
            )
            await interaction.response.send_message(
                f"Validation error: {exc}", ephemeral=True
            )
            return

        if response.confirmation_token is None:
            await interaction.response.send_message(response.markdown, ephemeral=True)
            return

        view = ConfirmApplyView(
            self.service,
            response.confirmation_token,
            timeout=float(self.settings.confirm_ttl_seconds),
        )
        await interaction.response.send_message(
            response.markdown, view=view, ephemeral=True
        )


def create_client(settings: Settings) -> SchemaBot:
    return SchemaBot(settings=settings)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
