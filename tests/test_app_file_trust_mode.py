from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from typing import Any, cast

import bot.app as app_module


def _always_admin(user: object) -> bool:
    _ = user
    return True


def _snapshot(guild: object) -> object:
    _ = guild
    return SimpleNamespace(guild=SimpleNamespace(name="Guild"))


async def _passthrough_confirmation(
    interaction: object,
    *,
    uploaded: bytes,
    command_name: str,
    locale: str,
) -> bytes | None:
    _ = interaction
    _ = command_name
    _ = locale
    return uploaded


async def _cancel_confirmation(
    interaction: object,
    *,
    uploaded: bytes,
    command_name: str,
    locale: str,
) -> bytes | None:
    _ = interaction
    _ = uploaded
    _ = command_name
    _ = locale
    return None


async def _override_confirmation(
    interaction: object,
    *,
    uploaded: bytes,
    command_name: str,
    locale: str,
) -> bytes | None:
    _ = interaction
    _ = uploaded
    _ = command_name
    _ = locale
    return b"rewritten"


class _FakeResponse:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.deferred: list[dict[str, object]] = []

    async def send_message(self, content: str, **kwargs: object) -> None:
        self.messages.append({"content": content, **kwargs})

    async def defer(self, **kwargs: object) -> None:
        self.deferred.append(dict(kwargs))


class _FakeFollowup:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send(self, content: str, **kwargs: object) -> None:
        self.messages.append({"content": content, **kwargs})


class _FakeInteraction:
    def __init__(self) -> None:
        self.guild: SimpleNamespace | None = SimpleNamespace(id=123)
        self.user = SimpleNamespace(id=456)
        self.locale = "en-US"
        self.response = _FakeResponse()
        self.followup = _FakeFollowup()


class _FakeJapaneseInteraction(_FakeInteraction):
    def __init__(self) -> None:
        super().__init__()
        self.locale = "ja"


class _FakeAttachment:
    def __init__(self, payload: bytes) -> None:
        self.filename = "schema.yaml"
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


def _attached_filename(message: dict[str, object]) -> str:
    file_obj = cast(Any, message["file"])
    return str(file_obj.filename)


def _assert_export_style_result_filename(filename: str, suffix: str) -> None:
    assert re.fullmatch(
        rf"Guild-\d{{8}}_\d{{6}}_{re.escape(suffix)}\.md",
        filename,
    )


class _FakeService:
    def __init__(self) -> None:
        self.export_calls: list[dict[str, object]] = []
        self.diff_calls: list[dict[str, object]] = []
        self.apply_calls: list[dict[str, object]] = []
        self.diff_markdown = "diff-ok"
        self.apply_markdown = "apply-ok"

    def export_schema(
        self,
        current: object,
        *,
        invoker_is_admin: bool,
        fields: object | None = None,
        locale: str = "en",
    ) -> object:
        self.export_calls.append(
            {
                "current": current,
                "invoker_is_admin": invoker_is_admin,
                "fields": fields,
                "locale": locale,
            }
        )
        return SimpleNamespace(
            markdown="export-ok",
            file=SimpleNamespace(filename="guild-schema.yaml", content=b"schema"),
        )

    def diff_schema(
        self,
        current: object,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        file_trust_mode: bool = False,
        prefer_name_matching: bool = False,
        locale: str = "en",
    ) -> object:
        self.diff_calls.append(
            {
                "current": current,
                "uploaded": uploaded,
                "invoker_is_admin": invoker_is_admin,
                "file_trust_mode": file_trust_mode,
                "prefer_name_matching": prefer_name_matching,
                "locale": locale,
            }
        )
        return SimpleNamespace(markdown=self.diff_markdown)

    def apply_schema_preview(
        self,
        current: object,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        invoker_id: int,
        file_trust_mode: bool = False,
        prefer_name_matching: bool = False,
        locale: str = "en",
    ) -> object:
        self.apply_calls.append(
            {
                "current": current,
                "uploaded": uploaded,
                "invoker_is_admin": invoker_is_admin,
                "invoker_id": invoker_id,
                "file_trust_mode": file_trust_mode,
                "prefer_name_matching": prefer_name_matching,
                "locale": locale,
            }
        )
        return SimpleNamespace(markdown=self.apply_markdown, confirmation_token=None)


def test_handle_export_defers_and_uses_followup(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_bot = SimpleNamespace(
        service=fake_service,
        _maybe_confirm_guild_id_override=_passthrough_confirmation,
    )
    interaction = _FakeInteraction()

    monkeypatch.setattr(app_module, "member_is_guild_admin", _always_admin)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        _snapshot,
    )

    asyncio.run(
        getattr(app_module.SchemaBot, "_handle_export")(
            fake_bot,
            interaction,
            include_name=True,
            include_permissions=True,
            include_role_overwrites=True,
            include_other_settings=True,
        )
    )

    assert len(fake_service.export_calls) == 1
    assert fake_service.export_calls[0]["locale"] == "en"
    assert interaction.response.deferred == [{"ephemeral": True}]
    assert interaction.followup.messages[0]["content"] == "export-ok"


def test_handle_diff_passes_file_trust_mode_to_service(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_bot = SimpleNamespace(
        service=fake_service,
        _maybe_confirm_guild_id_override=_passthrough_confirmation,
    )
    interaction = _FakeInteraction()
    attachment = _FakeAttachment(b"test")

    monkeypatch.setattr(app_module, "member_is_guild_admin", _always_admin)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        _snapshot,
    )

    asyncio.run(
        getattr(app_module.SchemaBot, "_handle_diff")(
            fake_bot,
            interaction,
            attachment,
            file_trust_mode=True,
        )
    )

    assert len(fake_service.diff_calls) == 1
    assert fake_service.diff_calls[0]["file_trust_mode"] is True
    assert fake_service.diff_calls[0]["prefer_name_matching"] is False
    assert fake_service.diff_calls[0]["locale"] == "en"
    assert interaction.response.deferred == [{"ephemeral": True}]
    assert interaction.followup.messages[0]["content"] == "diff-ok"
    _assert_export_style_result_filename(
        _attached_filename(interaction.followup.messages[0]),
        "diff",
    )


def test_handle_apply_passes_file_trust_mode_to_service(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_bot = SimpleNamespace(
        service=fake_service,
        _maybe_confirm_guild_id_override=_passthrough_confirmation,
    )
    interaction = _FakeInteraction()
    attachment = _FakeAttachment(b"test")

    monkeypatch.setattr(app_module, "member_is_guild_admin", _always_admin)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        _snapshot,
    )

    asyncio.run(
        getattr(app_module.SchemaBot, "_handle_apply")(
            fake_bot,
            interaction,
            attachment,
            file_trust_mode=True,
        )
    )

    assert len(fake_service.apply_calls) == 1
    assert fake_service.apply_calls[0]["file_trust_mode"] is True
    assert fake_service.apply_calls[0]["prefer_name_matching"] is False
    assert fake_service.apply_calls[0]["locale"] == "en"
    assert interaction.response.deferred == [{"ephemeral": True}]
    assert interaction.followup.messages[0]["content"] == "apply-ok"
    _assert_export_style_result_filename(
        _attached_filename(interaction.followup.messages[0]),
        "apply",
    )


def test_handle_diff_stops_when_guild_id_override_not_confirmed(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_bot = SimpleNamespace(
        service=fake_service,
        _maybe_confirm_guild_id_override=_cancel_confirmation,
    )
    interaction = _FakeInteraction()
    attachment = _FakeAttachment(b"test")

    monkeypatch.setattr(app_module, "member_is_guild_admin", _always_admin)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        _snapshot,
    )

    asyncio.run(
        getattr(app_module.SchemaBot, "_handle_diff")(
            fake_bot,
            interaction,
            attachment,
            file_trust_mode=False,
        )
    )

    assert fake_service.diff_calls == []
    assert interaction.response.deferred == [{"ephemeral": True}]


def test_handle_apply_uses_overridden_payload_after_guild_id_confirmation(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_bot = SimpleNamespace(
        service=fake_service,
        _maybe_confirm_guild_id_override=_override_confirmation,
    )
    interaction = _FakeInteraction()
    attachment = _FakeAttachment(b"guild:\n  id: '999'\n")

    monkeypatch.setattr(app_module, "member_is_guild_admin", _always_admin)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        _snapshot,
    )

    asyncio.run(
        getattr(app_module.SchemaBot, "_handle_apply")(
            fake_bot,
            interaction,
            attachment,
            file_trust_mode=False,
        )
    )

    assert len(fake_service.apply_calls) == 1
    assert fake_service.apply_calls[0]["uploaded"] == b"rewritten"
    assert fake_service.apply_calls[0]["prefer_name_matching"] is True
    _assert_export_style_result_filename(
        _attached_filename(interaction.followup.messages[0]),
        "apply",
    )


def test_handle_diff_enables_name_priority_after_guild_id_confirmation(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_bot = SimpleNamespace(
        service=fake_service,
        _maybe_confirm_guild_id_override=_override_confirmation,
    )
    interaction = _FakeInteraction()
    attachment = _FakeAttachment(b"guild:\n  id: '999'\n")

    monkeypatch.setattr(app_module, "member_is_guild_admin", _always_admin)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        _snapshot,
    )

    asyncio.run(
        getattr(app_module.SchemaBot, "_handle_diff")(
            fake_bot,
            interaction,
            attachment,
            file_trust_mode=False,
        )
    )

    assert len(fake_service.diff_calls) == 1
    assert fake_service.diff_calls[0]["uploaded"] == b"rewritten"
    assert fake_service.diff_calls[0]["prefer_name_matching"] is True
    _assert_export_style_result_filename(
        _attached_filename(interaction.followup.messages[0]),
        "diff",
    )


def test_handle_diff_uses_file_notice_for_long_result(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_service.diff_markdown = "x" * 2001
    fake_bot = SimpleNamespace(
        service=fake_service,
        _maybe_confirm_guild_id_override=_passthrough_confirmation,
    )
    interaction = _FakeInteraction()
    attachment = _FakeAttachment(b"test")

    monkeypatch.setattr(app_module, "member_is_guild_admin", _always_admin)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        _snapshot,
    )

    asyncio.run(
        getattr(app_module.SchemaBot, "_handle_diff")(
            fake_bot,
            interaction,
            attachment,
            file_trust_mode=False,
        )
    )

    assert interaction.followup.messages[0]["content"] == (
        "Result is attached as a file because it is too long to display inline."
    )
    _assert_export_style_result_filename(
        _attached_filename(interaction.followup.messages[0]),
        "diff",
    )


def test_handle_export_replies_with_japanese_guild_required_message() -> None:
    interaction = _FakeJapaneseInteraction()
    interaction.guild = None
    fake_bot = SimpleNamespace(service=_FakeService())

    asyncio.run(
        getattr(app_module.SchemaBot, "_handle_export")(
            fake_bot,
            interaction,
            include_name=True,
            include_permissions=True,
            include_role_overwrites=True,
            include_other_settings=True,
        )
    )

    assert interaction.response.messages == [
        {
            "content": "このコマンドはギルド内でのみ使用できます。",
            "ephemeral": True,
        }
    ]
