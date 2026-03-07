from __future__ import annotations

import asyncio
import logging

import pytest

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


def test_execute_plan_logs_failed_operation(caplog: pytest.LogCaptureFixture) -> None:
    plan = ApplyPlan(
        operations=[
            ApplyOperation(
                operation_id="1",
                action="Delete",
                target_type="channel",
                target_id="bad",
                before={"name": "x"},
                after=None,
                risk="high",
            ),
        ]
    )

    caplog.set_level(logging.INFO, logger="bot.executor.engine")
    execute_plan(plan, b"backup", MixedExecutor())

    assert "apply.operation.failed operation_id=1" in caplog.text
    assert "apply.plan.completed mode=sync applied=0 failed=1 skipped=0" in caplog.text


def test_execute_plan_collects_skipped(caplog: pytest.LogCaptureFixture) -> None:
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

    caplog.set_level(logging.INFO, logger="bot.executor.engine")
    report = execute_plan(plan, b"backup", SkippingExecutor())

    assert len(report.applied) == 0
    assert len(report.failed) == 0
    assert len(report.skipped) == 1
    assert report.skipped[0]["operation_id"] == "1"
    assert "apply.operation.skipped operation_id=1" in caplog.text
    assert "apply.plan.completed mode=sync applied=0 failed=0 skipped=1" in caplog.text


def test_execute_plan_async_collects_applied_failed_and_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
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

    caplog.set_level(logging.INFO, logger="bot.executor.engine")
    report = asyncio.run(execute_plan_async(plan, b"backup", AsyncMixedExecutor()))

    assert len(report.applied) == 1
    assert len(report.skipped) == 1
    assert len(report.failed) == 1
    assert report.skipped[0]["operation_id"] == "2"
    assert report.failed[0]["operation_id"] == "3"
    assert "apply.operation.skipped operation_id=2" in caplog.text
    assert "apply.operation.failed operation_id=3" in caplog.text
    assert "apply.plan.completed mode=async applied=1 failed=1 skipped=1" in caplog.text
