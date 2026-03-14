from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from bot.usecases.diff.models import DiffResult
from bot.usecases.planner.models import ApplyPlan
from bot.usecases.schema_model.models import GuildSchema


class SessionError(RuntimeError):
    pass


class SessionNotFoundError(SessionError):
    pass


class SessionExpiredError(SessionError):
    pass


class SessionForbiddenError(SessionError):
    pass


@dataclass(slots=True)
class PendingApplySession:
    token: str
    invoker_id: int
    created_at: datetime
    expires_at: datetime
    desired_schema: GuildSchema
    diff_result: DiffResult
    apply_plan: ApplyPlan


class InMemorySessionStore:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, PendingApplySession] = {}

    def create(
        self,
        invoker_id: int,
        desired_schema: GuildSchema,
        diff_result: DiffResult,
        apply_plan: ApplyPlan,
        now: datetime | None = None,
    ) -> PendingApplySession:
        current = now or datetime.now(timezone.utc)
        token = token_urlsafe(20)
        session = PendingApplySession(
            token=token,
            invoker_id=invoker_id,
            created_at=current,
            expires_at=current + timedelta(seconds=self._ttl_seconds),
            desired_schema=desired_schema,
            diff_result=diff_result,
            apply_plan=apply_plan,
        )
        self._store[token] = session
        return session

    def get(self, token: str, now: datetime | None = None) -> PendingApplySession:
        session = self._store.get(token)
        if session is None:
            raise SessionNotFoundError("confirmation session not found")

        current = now or datetime.now(timezone.utc)
        if current > session.expires_at:
            self._store.pop(token, None)
            raise SessionExpiredError("confirmation expired")

        return session

    def consume(
        self, token: str, invoker_id: int, now: datetime | None = None
    ) -> PendingApplySession:
        session = self.get(token, now=now)
        if session.invoker_id != invoker_id:
            raise SessionForbiddenError("only the original invoker can confirm")
        self._store.pop(token, None)
        return session
