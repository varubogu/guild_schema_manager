from __future__ import annotations

import asyncio

from bot.executor import SkipOperationError, execute_plan, execute_plan_async
from bot.planner.models import ApplyOperation, ApplyPlan


class MixedExecutor:
    def execute(self, operation: ApplyOperation) -> None:
        if operation.target_id == "bad":
            raise RuntimeError("boom")


class SkippingExecutor:
    def execute(self, operation: ApplyOperation) -> None:
        if operation.target_id == "skip":
            raise SkipOperationError("missing dependency")


class AsyncMixedExecutor:
    async def execute(self, operation: ApplyOperation) -> None:
        if operation.target_id == "skip":
            raise SkipOperationError("owner missing")
        if operation.target_id == "bad":
            raise RuntimeError("boom")


def test_execute_plan_collects_partial_failures() -> None:
    plan = ApplyPlan(
        operations=[
            ApplyOperation(
                operation_id="1",
                action="Create",
                target_type="role",
                target_id="ok",
                before=None,
                after={"name": "a"},
                risk="low",
            ),
            ApplyOperation(
                operation_id="2",
                action="Delete",
                target_type="channel",
                target_id="bad",
                before={"name": "x"},
                after=None,
                risk="high",
            ),
        ]
    )

    report = execute_plan(plan, b"backup", MixedExecutor())

    assert len(report.applied) == 1
    assert len(report.failed) == 1
    assert report.failed[0]["operation_id"] == "2"


def test_execute_plan_collects_skipped() -> None:
    plan = ApplyPlan(
        operations=[
            ApplyOperation(
                operation_id="1",
                action="Create",
                target_type="role",
                target_id="skip",
                before=None,
                after={"name": "a"},
                risk="low",
            ),
        ]
    )

    report = execute_plan(plan, b"backup", SkippingExecutor())

    assert len(report.applied) == 0
    assert len(report.failed) == 0
    assert len(report.skipped) == 1
    assert report.skipped[0]["operation_id"] == "1"


def test_execute_plan_async_collects_applied_failed_and_skipped() -> None:
    plan = ApplyPlan(
        operations=[
            ApplyOperation(
                operation_id="1",
                action="Create",
                target_type="role",
                target_id="ok",
                before=None,
                after={"name": "a"},
                risk="low",
            ),
            ApplyOperation(
                operation_id="2",
                action="Update",
                target_type="channel",
                target_id="skip",
                before={"name": "x"},
                after={"name": "y"},
                risk="medium",
            ),
            ApplyOperation(
                operation_id="3",
                action="Delete",
                target_type="channel",
                target_id="bad",
                before={"name": "z"},
                after=None,
                risk="high",
            ),
        ]
    )

    report = asyncio.run(execute_plan_async(plan, b"backup", AsyncMixedExecutor()))

    assert len(report.applied) == 1
    assert len(report.skipped) == 1
    assert len(report.failed) == 1
    assert report.skipped[0]["operation_id"] == "2"
    assert report.failed[0]["operation_id"] == "3"
