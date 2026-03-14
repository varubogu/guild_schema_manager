from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import discord
import pytest

from bot.usecases.executor import SkipOperationError
from bot.usecases.executor.discord_executor import (
    DiscordGuildExecutor,
    ROLE_HIERARCHY_SKIP_REASON,
)
from bot.usecases.planner.models import ApplyOperation


class _FakeRole:
    def __init__(
        self,
        *,
        role_id: int,
        name: str,
        position: int,
        edit_error: Exception | None = None,
    ) -> None:
        self.id = role_id
        self.name = name
        self.position = position
        self._edit_error = edit_error
        self.edits: list[dict[str, object]] = []

    async def edit(self, **kwargs: object) -> None:
        if self._edit_error is not None:
            raise self._edit_error
        self.edits.append(dict(kwargs))
        position = kwargs.get("position")
        if isinstance(position, int):
            self.position = position


class _FakeGuild:
    def __init__(
        self,
        *,
        top_position: int,
        roles: list[_FakeRole] | None = None,
        created_role: _FakeRole | None = None,
    ) -> None:
        self.me = SimpleNamespace(top_role=SimpleNamespace(position=top_position))
        self.roles = roles or []
        self._created_role = created_role or _FakeRole(
            role_id=999,
            name="created",
            position=0,
        )
        self.create_role_calls: list[dict[str, object]] = []

    async def create_role(self, **kwargs: object) -> _FakeRole:
        self.create_role_calls.append(dict(kwargs))
        return self._created_role

    def get_role(self, role_id: int) -> _FakeRole | None:
        for role in self.roles:
            if role.id == role_id:
                return role
        return None


def _role_operation(
    *,
    action: str,
    target_id: str | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> ApplyOperation:
    return ApplyOperation(
        operation_id="op-1",
        action=action,
        target_type="role",
        target_id=target_id,
        before=before,
        after=after,
        risk="low",
    )


def _role_forbidden_error() -> discord.Forbidden:
    response = cast(Any, SimpleNamespace(status=403, reason="Forbidden"))
    return discord.Forbidden(
        response,
        {
            "message": "Missing Permissions",
            "code": 50013,
        },
    )


def test_create_role_clamps_position_to_bot_top_minus_one() -> None:
    created_role = _FakeRole(role_id=500, name="new-role", position=0)
    guild = _FakeGuild(top_position=5, created_role=created_role)
    executor = DiscordGuildExecutor(cast(discord.Guild, guild))
    operation = _role_operation(
        action="Create",
        target_id=None,
        before=None,
        after={"name": "new-role", "position": 42},
    )

    asyncio.run(executor.execute(operation))

    assert len(guild.create_role_calls) == 1
    assert created_role.edits == [{"position": 4}]


def test_update_role_skips_when_target_is_at_or_above_bot_top_position() -> None:
    role = _FakeRole(role_id=100, name="Moderators", position=5)
    guild = _FakeGuild(top_position=5, roles=[role])
    executor = DiscordGuildExecutor(cast(discord.Guild, guild))
    operation = _role_operation(
        action="Update",
        target_id="100",
        before={"name": "Moderators"},
        after={"name": "Moderators2"},
    )

    with pytest.raises(SkipOperationError, match=ROLE_HIERARCHY_SKIP_REASON):
        asyncio.run(executor.execute(operation))

    assert role.edits == []


def test_reorder_role_skips_when_target_is_at_or_above_bot_top_position() -> None:
    role = _FakeRole(role_id=100, name="Moderators", position=7)
    guild = _FakeGuild(top_position=6, roles=[role])
    executor = DiscordGuildExecutor(cast(discord.Guild, guild))
    operation = _role_operation(
        action="Reorder",
        target_id="100",
        before={"position": 7},
        after={"position": 3},
    )

    with pytest.raises(SkipOperationError, match=ROLE_HIERARCHY_SKIP_REASON):
        asyncio.run(executor.execute(operation))

    assert role.edits == []


def test_role_forbidden_is_translated_to_role_hierarchy_skip() -> None:
    role = _FakeRole(
        role_id=100,
        name="Moderators",
        position=1,
        edit_error=_role_forbidden_error(),
    )
    guild = _FakeGuild(top_position=5, roles=[role])
    executor = DiscordGuildExecutor(cast(discord.Guild, guild))
    operation = _role_operation(
        action="Update",
        target_id="100",
        before={"name": "Moderators"},
        after={"name": "Moderators2"},
    )

    with pytest.raises(SkipOperationError, match=ROLE_HIERARCHY_SKIP_REASON):
        asyncio.run(executor.execute(operation))
