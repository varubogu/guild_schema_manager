from __future__ import annotations

from bot.usecases.planner.models import ApplyOperation


class NoopExecutor:
    def execute(self, operation: ApplyOperation) -> None:
        _ = operation
