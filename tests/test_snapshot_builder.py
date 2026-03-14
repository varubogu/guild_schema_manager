from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from bot.usecases.snapshot import build_snapshot_from_guild


def _role(
    *,
    role_id: int,
    name: str,
    is_bot_managed: bool | None = None,
    tag_bot_id: int | None = None,
) -> Any:
    payload: dict[str, object] = {
        "id": role_id,
        "name": name,
        "permissions": [],
        "color": SimpleNamespace(value=0),
        "hoist": False,
        "mentionable": False,
        "position": 1,
    }
    if is_bot_managed is not None:
        payload["is_bot_managed"] = lambda: is_bot_managed
    payload["tags"] = None if tag_bot_id is None else SimpleNamespace(bot_id=tag_bot_id)
    return SimpleNamespace(**payload)


def test_build_snapshot_uses_is_bot_managed_method_when_available() -> None:
    guild = SimpleNamespace(
        id=1,
        name="Guild",
        roles=[
            _role(
                role_id=10,
                name="ManagedByMethod",
                is_bot_managed=True,
                tag_bot_id=None,
            )
        ],
        categories=[],
        channels=[],
    )

    snapshot = build_snapshot_from_guild(guild)

    assert snapshot.roles[0].bot_managed is True


def test_build_snapshot_falls_back_to_role_tags_bot_id() -> None:
    guild = SimpleNamespace(
        id=1,
        name="Guild",
        roles=[
            _role(
                role_id=11,
                name="ManagedByTags",
                is_bot_managed=None,
                tag_bot_id=999,
            )
        ],
        categories=[],
        channels=[],
    )

    snapshot = build_snapshot_from_guild(guild)

    assert snapshot.roles[0].bot_managed is True
