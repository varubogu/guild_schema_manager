from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import bot.app as app_module


class _FakeResponse:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_message(self, content: str, **kwargs: object) -> None:
        self.messages.append({"content": content, **kwargs})


class _FakeInteraction:
    def __init__(self) -> None:
        self.guild = SimpleNamespace(id=123)
        self.user = SimpleNamespace(id=456)
        self.response = _FakeResponse()


class _FakeAttachment:
    def __init__(self, payload: bytes) -> None:
        self.filename = "schema.yaml"
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _FakeService:
    def __init__(self) -> None:
        self.diff_calls: list[dict[str, object]] = []
        self.apply_calls: list[dict[str, object]] = []

    def diff_schema(
        self,
        current: object,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        file_trust_mode: bool = False,
    ) -> object:
        self.diff_calls.append(
            {
                "current": current,
                "uploaded": uploaded,
                "invoker_is_admin": invoker_is_admin,
                "file_trust_mode": file_trust_mode,
            }
        )
        return SimpleNamespace(markdown="diff-ok")

    def apply_schema_preview(
        self,
        current: object,
        uploaded: bytes,
        *,
        invoker_is_admin: bool,
        invoker_id: int,
        file_trust_mode: bool = False,
    ) -> object:
        self.apply_calls.append(
            {
                "current": current,
                "uploaded": uploaded,
                "invoker_is_admin": invoker_is_admin,
                "invoker_id": invoker_id,
                "file_trust_mode": file_trust_mode,
            }
        )
        return SimpleNamespace(markdown="apply-ok", confirmation_token=None)


def test_handle_diff_passes_file_trust_mode_to_service(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_bot = SimpleNamespace(service=fake_service)
    interaction = _FakeInteraction()
    attachment = _FakeAttachment(b"test")

    monkeypatch.setattr(app_module, "member_is_guild_admin", lambda user: True)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        lambda guild: "snapshot",
    )

    asyncio.run(
        app_module.SchemaBot._handle_diff(
            fake_bot,
            interaction,
            attachment,
            file_trust_mode=True,
        )
    )

    assert len(fake_service.diff_calls) == 1
    assert fake_service.diff_calls[0]["file_trust_mode"] is True
    assert interaction.response.messages[0]["content"] == "diff-ok"


def test_handle_apply_passes_file_trust_mode_to_service(
    monkeypatch: Any,
) -> None:
    fake_service = _FakeService()
    fake_bot = SimpleNamespace(service=fake_service)
    interaction = _FakeInteraction()
    attachment = _FakeAttachment(b"test")

    monkeypatch.setattr(app_module, "member_is_guild_admin", lambda user: True)
    monkeypatch.setattr(
        app_module,
        "build_snapshot_from_guild",
        lambda guild: "snapshot",
    )

    asyncio.run(
        app_module.SchemaBot._handle_apply(
            fake_bot,
            interaction,
            attachment,
            file_trust_mode=True,
        )
    )

    assert len(fake_service.apply_calls) == 1
    assert fake_service.apply_calls[0]["file_trust_mode"] is True
    assert interaction.response.messages[0]["content"] == "apply-ok"
