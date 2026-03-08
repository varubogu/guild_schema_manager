from __future__ import annotations

import io
import logging

import discord
from discord import app_commands

from bot.commands import (
    ExportFieldSelection,
    SchemaCommandService,
    extract_uploaded_guild_id,
    overwrite_uploaded_guild_id,
)
from bot.config import Settings
from bot.executor.discord_executor import DiscordGuildExecutor
from bot.executor.noop import NoopExecutor
from bot.localization import SupportedLocale, resolve_user_locale, t
from bot.logging_utils import log_async_lifecycle
from bot.security import AuthorizationError, member_is_guild_admin
from bot.session_store import InMemorySessionStore
from bot.snapshot import build_snapshot_from_guild

logger = logging.getLogger(__name__)

LOCALIZATION_KEY = "key"


def _localized(key: str) -> app_commands.locale_str:
    return app_commands.locale_str(t(key, "en"), key=key)


GROUP_DESCRIPTION = _localized("schema.group.description")
EXPORT_DESCRIPTION = _localized("schema.command.export.description")
DIFF_DESCRIPTION = _localized("schema.command.diff.description")
APPLY_DESCRIPTION = _localized("schema.command.apply.description")
SCHEMA_FILE_DESCRIPTION = _localized("schema.argument.file.description")
FILE_TRUST_MODE_DESCRIPTION = _localized("schema.argument.file_trust_mode.description")
EXPORT_INCLUDE_NAME_DESCRIPTION = _localized(
    "schema.argument.export.include_name.description"
)
EXPORT_INCLUDE_PERMISSIONS_DESCRIPTION = _localized(
    "schema.argument.export.include_permissions.description"
)
EXPORT_INCLUDE_ROLE_OVERWRITES_DESCRIPTION = _localized(
    "schema.argument.export.include_role_overwrites.description"
)
EXPORT_INCLUDE_OTHER_SETTINGS_DESCRIPTION = _localized(
    "schema.argument.export.include_other_settings.description"
)


class SchemaCommandTranslator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None:
        _ = context
        key = string.extras.get(LOCALIZATION_KEY)
        if not isinstance(key, str):
            return None

        locale_code = resolve_user_locale(locale)
        if locale_code != "ja":
            return None

        translated = t(key, locale_code)
        if translated == key:
            return None
        return translated


def _interaction_locale(interaction: discord.Interaction) -> SupportedLocale:
    return resolve_user_locale(getattr(interaction, "locale", None))


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


def _export_command_context(
    self: "SchemaBot",
    interaction: discord.Interaction,
    include_name: bool,
    include_permissions: bool,
    include_role_overwrites: bool,
    include_other_settings: bool,
) -> dict[str, object]:
    _ = self
    return {
        **_interaction_context(interaction),
        "include_name": include_name,
        "include_permissions": include_permissions,
        "include_role_overwrites": include_role_overwrites,
        "include_other_settings": include_other_settings,
    }


def _file_command_context(
    self: "SchemaBot",
    interaction: discord.Interaction,
    file: discord.Attachment,
    file_trust_mode: bool,
) -> dict[str, object]:
    _ = self
    return {
        **_interaction_context(interaction),
        "filename": file.filename,
        "file_trust_mode": file_trust_mode,
    }


class GuildIdOverrideView(discord.ui.View):
    def __init__(
        self,
        *,
        invoker_id: int,
        timeout: float,
        locale: SupportedLocale,
    ) -> None:
        super().__init__(timeout=timeout)
        self._invoker_id = invoker_id
        self._locale: SupportedLocale = locale
        self.decision: bool | None = None

        approve_button = discord.ui.Button[GuildIdOverrideView](
            label=t("ui.button.guild_id_override.approve", locale),
            style=discord.ButtonStyle.success,
        )
        cancel_button = discord.ui.Button[GuildIdOverrideView](
            label=t("ui.button.cancel", locale),
            style=discord.ButtonStyle.secondary,
        )

        async def on_approve(interaction: discord.Interaction) -> None:
            await self.approve(interaction, approve_button)

        async def on_cancel(interaction: discord.Interaction) -> None:
            await self.cancel(interaction, cancel_button)

        approve_button.callback = on_approve
        cancel_button.callback = on_cancel
        self.add_item(approve_button)
        self.add_item(cancel_button)

    async def _reject_non_invoker(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self._invoker_id:
            return False
        response_locale = _interaction_locale(interaction)
        await interaction.response.send_message(
            t("ui.error.invoker_only_confirmation_response", response_locale),
            ephemeral=True,
        )
        return True

    async def approve(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[GuildIdOverrideView],
    ) -> None:
        _ = button
        if await self._reject_non_invoker(interaction):
            return
        self.decision = True
        await interaction.response.edit_message(
            content=t("ui.guild_id_override.approved", self._locale),
            view=None,
        )
        self.stop()

    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[GuildIdOverrideView],
    ) -> None:
        _ = button
        if await self._reject_non_invoker(interaction):
            return
        self.decision = False
        await interaction.response.edit_message(
            content=t("ui.guild_id_override.canceled", self._locale),
            view=None,
        )
        self.stop()


class ConfirmApplyView(discord.ui.View):
    def __init__(
        self,
        service: SchemaCommandService,
        token: str,
        *,
        timeout: float,
        locale: SupportedLocale,
    ) -> None:
        super().__init__(timeout=timeout)
        self._service = service
        self._token = token
        self._locale: SupportedLocale = locale

        button = discord.ui.Button[ConfirmApplyView](
            label=t("ui.button.confirm_apply", locale),
            style=discord.ButtonStyle.danger,
        )

        async def on_confirm(interaction: discord.Interaction) -> None:
            await self.confirm(interaction, button)

        button.callback = on_confirm
        self.add_item(button)

    @log_async_lifecycle(
        logger,
        "command.schema.apply.confirm",
        _confirm_context,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[ConfirmApplyView],
    ) -> None:
        _ = button
        locale = _interaction_locale(interaction)
        if interaction.guild is None:
            logger.warning(
                "command.schema.apply.confirm rejected reason=guild_required"
            )
            await interaction.response.send_message(
                t("ui.error.guild_required", locale), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = await self._service.confirm_apply_async(
                self._token,
                invoker_id=interaction.user.id,
                current=snapshot,
                executor=DiscordGuildExecutor(interaction.guild),
                locale=locale,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "command.schema.apply.confirm failed guild_id=%s user_id=%s",
                interaction.guild.id,
                interaction.user.id,
            )
            await interaction.followup.send(
                t("ui.error.apply_unexpected", locale),
                ephemeral=True,
            )
            return

        files: list[discord.File] = []
        if response.backup_file is not None:
            files.append(
                discord.File(
                    fp=io.BytesIO(response.backup_file.content),
                    filename=response.backup_file.filename,
                )
            )

        await interaction.followup.send(response.markdown, files=files, ephemeral=True)

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
            schema_hint_url_template=settings.schema_hint_url_template,
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
        @app_commands.describe(
            include_name=EXPORT_INCLUDE_NAME_DESCRIPTION,
            include_permissions=EXPORT_INCLUDE_PERMISSIONS_DESCRIPTION,
            include_role_overwrites=EXPORT_INCLUDE_ROLE_OVERWRITES_DESCRIPTION,
            include_other_settings=EXPORT_INCLUDE_OTHER_SETTINGS_DESCRIPTION,
        )
        async def export(  # pyright: ignore[reportUnusedFunction]
            interaction: discord.Interaction,
            include_name: bool = True,
            include_permissions: bool = True,
            include_role_overwrites: bool = True,
            include_other_settings: bool = True,
        ) -> None:
            await self._handle_export(
                interaction,
                include_name=include_name,
                include_permissions=include_permissions,
                include_role_overwrites=include_role_overwrites,
                include_other_settings=include_other_settings,
            )

        @schema_group.command(
            name="diff",
            description=DIFF_DESCRIPTION,
        )
        @app_commands.describe(
            file=SCHEMA_FILE_DESCRIPTION,
            file_trust_mode=FILE_TRUST_MODE_DESCRIPTION,
        )
        async def diff(  # pyright: ignore[reportUnusedFunction]
            interaction: discord.Interaction,
            file: discord.Attachment,
            file_trust_mode: bool = False,
        ) -> None:
            await self._handle_diff(interaction, file, file_trust_mode=file_trust_mode)

        @schema_group.command(
            name="apply",
            description=APPLY_DESCRIPTION,
        )
        @app_commands.describe(
            file=SCHEMA_FILE_DESCRIPTION,
            file_trust_mode=FILE_TRUST_MODE_DESCRIPTION,
        )
        async def apply(  # pyright: ignore[reportUnusedFunction]
            interaction: discord.Interaction,
            file: discord.Attachment,
            file_trust_mode: bool = False,
        ) -> None:
            await self._handle_apply(interaction, file, file_trust_mode=file_trust_mode)

        self.tree.add_command(schema_group)
        await self.tree.sync()

    @log_async_lifecycle(logger, "event.on_ready")
    async def on_ready(self) -> None:
        logger.info(
            "bot.ready guild_count=%d user_id=%s",
            len(self.guilds),
            getattr(self.user, "id", None),
        )

    async def _maybe_confirm_guild_id_override(
        self,
        interaction: discord.Interaction,
        *,
        uploaded: bytes,
        command_name: str,
        locale: SupportedLocale,
    ) -> bytes | None:
        if interaction.guild is None:
            return None
        uploaded_guild_id = extract_uploaded_guild_id(uploaded)
        if uploaded_guild_id is None:
            return uploaded

        current_guild_id = str(interaction.guild.id)
        if uploaded_guild_id == current_guild_id:
            return uploaded

        logger.warning(
            "%s guild_id_mismatch uploaded=%s current=%s user_id=%s",
            command_name,
            uploaded_guild_id,
            current_guild_id,
            interaction.user.id,
        )
        view = GuildIdOverrideView(
            invoker_id=interaction.user.id,
            timeout=float(self.settings.confirm_ttl_seconds),
            locale=locale,
        )
        await interaction.followup.send(
            t(
                "ui.guild_id_override.prompt",
                locale,
                uploaded_guild_id=uploaded_guild_id,
                current_guild_id=current_guild_id,
            ),
            view=view,
            ephemeral=True,
        )

        timed_out = await view.wait()
        if timed_out or view.decision is None:
            await interaction.followup.send(
                t("ui.guild_id_override.timed_out", locale),
                ephemeral=True,
            )
            return None
        if not view.decision:
            return None
        return overwrite_uploaded_guild_id(uploaded, current_guild_id)

    @log_async_lifecycle(
        logger,
        "command.schema.export",
        _export_command_context,
    )
    async def _handle_export(
        self,
        interaction: discord.Interaction,
        include_name: bool,
        include_permissions: bool,
        include_role_overwrites: bool,
        include_other_settings: bool,
    ) -> None:
        locale = _interaction_locale(interaction)
        if interaction.guild is None:
            logger.warning("command.schema.export rejected reason=guild_required")
            await interaction.response.send_message(
                t("ui.error.guild_required", locale),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        is_admin = member_is_guild_admin(interaction.user)
        try:
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = self.service.export_schema(
                snapshot,
                invoker_is_admin=is_admin,
                fields=ExportFieldSelection(
                    include_name=include_name,
                    include_permissions=include_permissions,
                    include_role_overwrites=include_role_overwrites,
                    include_other_settings=include_other_settings,
                ),
                locale=locale,
            )
        except AuthorizationError as exc:
            logger.warning(
                "command.schema.export authorization_failed guild_id=%s user_id=%s error=%s",
                interaction.guild.id,
                interaction.user.id,
                exc,
            )
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        file_obj = discord.File(
            fp=io.BytesIO(response.file.content), filename=response.file.filename
        )
        await interaction.followup.send(
            response.markdown, file=file_obj, ephemeral=True
        )

    @log_async_lifecycle(
        logger,
        "command.schema.diff",
        _file_command_context,
    )
    async def _handle_diff(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        file_trust_mode: bool,
    ) -> None:
        locale = _interaction_locale(interaction)
        if interaction.guild is None:
            logger.warning("command.schema.diff rejected reason=guild_required")
            await interaction.response.send_message(
                t("ui.error.guild_required", locale),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        is_admin = member_is_guild_admin(interaction.user)
        try:
            uploaded = await file.read()
            uploaded = await self._maybe_confirm_guild_id_override(
                interaction,
                uploaded=uploaded,
                command_name="command.schema.diff",
                locale=locale,
            )
            if uploaded is None:
                return
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = self.service.diff_schema(
                snapshot,
                uploaded,
                invoker_is_admin=is_admin,
                file_trust_mode=file_trust_mode,
                locale=locale,
            )
        except AuthorizationError as exc:
            logger.warning(
                "command.schema.diff authorization_failed guild_id=%s user_id=%s error=%s",
                interaction.guild.id,
                interaction.user.id,
                exc,
            )
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "command.schema.diff validation_failed guild_id=%s user_id=%s filename=%s",
                interaction.guild.id,
                interaction.user.id,
                file.filename,
            )
            await interaction.followup.send(
                t("ui.error.validation", locale, error=str(exc)),
                ephemeral=True,
            )
            return

        await interaction.followup.send(response.markdown, ephemeral=True)

    @log_async_lifecycle(
        logger,
        "command.schema.apply",
        _file_command_context,
    )
    async def _handle_apply(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        file_trust_mode: bool,
    ) -> None:
        locale = _interaction_locale(interaction)
        if interaction.guild is None:
            logger.warning("command.schema.apply rejected reason=guild_required")
            await interaction.response.send_message(
                t("ui.error.guild_required", locale),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        is_admin = member_is_guild_admin(interaction.user)
        try:
            uploaded = await file.read()
            uploaded = await self._maybe_confirm_guild_id_override(
                interaction,
                uploaded=uploaded,
                command_name="command.schema.apply",
                locale=locale,
            )
            if uploaded is None:
                return
            snapshot = build_snapshot_from_guild(interaction.guild)
            response = self.service.apply_schema_preview(
                snapshot,
                uploaded,
                invoker_is_admin=is_admin,
                invoker_id=interaction.user.id,
                file_trust_mode=file_trust_mode,
                locale=locale,
            )
        except AuthorizationError as exc:
            logger.warning(
                "command.schema.apply authorization_failed guild_id=%s user_id=%s error=%s",
                interaction.guild.id,
                interaction.user.id,
                exc,
            )
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "command.schema.apply validation_failed guild_id=%s user_id=%s filename=%s",
                interaction.guild.id,
                interaction.user.id,
                file.filename,
            )
            await interaction.followup.send(
                t("ui.error.validation", locale, error=str(exc)),
                ephemeral=True,
            )
            return

        if response.confirmation_token is None:
            await interaction.followup.send(response.markdown, ephemeral=True)
            return

        view = ConfirmApplyView(
            self.service,
            response.confirmation_token,
            timeout=float(self.settings.confirm_ttl_seconds),
            locale=locale,
        )
        await interaction.followup.send(response.markdown, view=view, ephemeral=True)


def create_client(settings: Settings) -> SchemaBot:
    return SchemaBot(settings=settings)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
