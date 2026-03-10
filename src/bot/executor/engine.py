from __future__ import annotations

import logging
from typing import Protocol

from bot.planner.models import ApplyOperation, ApplyPlan, ApplyReport
from .errors import SkipOperationError

logger = logging.getLogger(__name__)


class OperationExecutor(Protocol):
    def execute(self, operation: ApplyOperation) -> None: ...


class AsyncOperationExecutor(Protocol):
    async def execute(self, operation: ApplyOperation) -> None: ...


def execute_plan(
    plan: ApplyPlan,
    backup_file: bytes,
    executor: OperationExecutor,
) -> ApplyReport:
    report = ApplyReport(backup_file=backup_file)

    for operation in plan.operations:
        if operation.skip_reason:
            logger.warning(
                "apply.operation.skipped operation_id=%s action=%s target_type=%s target_id=%s reason=%s",
                operation.operation_id,
                operation.action,
                operation.target_type,
                operation.target_id,
                operation.skip_reason,
            )
            report.skipped.append(
                {
                    "operation_id": operation.operation_id,
                    "target_type": operation.target_type,
                    "target_id": operation.target_id,
                    "reason": operation.skip_reason,
                }
            )
            continue
        try:
            executor.execute(operation)
        except SkipOperationError as exc:
            logger.warning(
                "apply.operation.skipped operation_id=%s action=%s target_type=%s target_id=%s reason=%s",
                operation.operation_id,
                operation.action,
                operation.target_type,
                operation.target_id,
                exc,
            )
            report.skipped.append(
                {
                    "operation_id": operation.operation_id,
                    "target_type": operation.target_type,
                    "target_id": operation.target_id,
                    "reason": str(exc),
                }
            )
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "apply.operation.failed operation_id=%s action=%s target_type=%s target_id=%s",
                operation.operation_id,
                operation.action,
                operation.target_type,
                operation.target_id,
            )
            report.failed.append(
                {
                    "operation_id": operation.operation_id,
                    "target_type": operation.target_type,
                    "target_id": operation.target_id,
                    "error": str(exc),
                }
            )
            continue

        report.applied.append(operation)

    logger.info(
        "apply.plan.completed mode=sync applied=%d failed=%d skipped=%d",
        len(report.applied),
        len(report.failed),
        len(report.skipped),
    )
    return report


async def execute_plan_async(
    plan: ApplyPlan,
    backup_file: bytes,
    executor: AsyncOperationExecutor,
) -> ApplyReport:
    report = ApplyReport(backup_file=backup_file)

    for operation in plan.operations:
        if operation.skip_reason:
            logger.warning(
                "apply.operation.skipped operation_id=%s action=%s target_type=%s target_id=%s reason=%s",
                operation.operation_id,
                operation.action,
                operation.target_type,
                operation.target_id,
                operation.skip_reason,
            )
            report.skipped.append(
                {
                    "operation_id": operation.operation_id,
                    "target_type": operation.target_type,
                    "target_id": operation.target_id,
                    "reason": operation.skip_reason,
                }
            )
            continue
        try:
            await executor.execute(operation)
        except SkipOperationError as exc:
            logger.warning(
                "apply.operation.skipped operation_id=%s action=%s target_type=%s target_id=%s reason=%s",
                operation.operation_id,
                operation.action,
                operation.target_type,
                operation.target_id,
                exc,
            )
            report.skipped.append(
                {
                    "operation_id": operation.operation_id,
                    "target_type": operation.target_type,
                    "target_id": operation.target_id,
                    "reason": str(exc),
                }
            )
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "apply.operation.failed operation_id=%s action=%s target_type=%s target_id=%s",
                operation.operation_id,
                operation.action,
                operation.target_type,
                operation.target_id,
            )
            report.failed.append(
                {
                    "operation_id": operation.operation_id,
                    "target_type": operation.target_type,
                    "target_id": operation.target_id,
                    "error": str(exc),
                }
            )
            continue

        report.applied.append(operation)

    logger.info(
        "apply.plan.completed mode=async applied=%d failed=%d skipped=%d",
        len(report.applied),
        len(report.failed),
        len(report.skipped),
    )
    return report
