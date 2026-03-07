from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from bot.diff.models import DiffResult
from bot.planner.models import ApplyPlan
from bot.schema import parse_schema_dict
from bot.session_store import InMemorySessionStore, SessionExpiredError, SessionNotFoundError


def sample_schema():
    return parse_schema_dict(
        {
            "version": 1,
            "guild": {"id": "1", "name": "Guild"},
            "roles": [],
            "categories": [],
            "channels": [],
        }
    )


def test_session_expires() -> None:
    store = InMemorySessionStore(ttl_seconds=1)
    session = store.create(
        invoker_id=1,
        desired_schema=sample_schema(),
        diff_result=DiffResult(summary={"Create": 0, "Update": 0, "Delete": 0, "Move": 0, "Reorder": 0}),
        apply_plan=ApplyPlan(operations=[]),
        now=datetime.now(timezone.utc),
    )

    with pytest.raises(SessionExpiredError):
        store.get(session.token, now=datetime.now(timezone.utc) + timedelta(seconds=2))


def test_restart_invalidates_pending_sessions() -> None:
    original_store = InMemorySessionStore(ttl_seconds=600)
    session = original_store.create(
        invoker_id=1,
        desired_schema=sample_schema(),
        diff_result=DiffResult(summary={"Create": 0, "Update": 0, "Delete": 0, "Move": 0, "Reorder": 0}),
        apply_plan=ApplyPlan(operations=[]),
    )

    restarted_store = InMemorySessionStore(ttl_seconds=600)
    with pytest.raises(SessionNotFoundError):
        restarted_store.get(session.token)
