from __future__ import annotations

from typing import Protocol

from bot.planner.models import ApplyOperation, ApplyPlan, ApplyReport
from .errors import SkipOperationError


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
        try:
            executor.execute(operation)
        except SkipOperationError as exc:
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

    return report


async def execute_plan_async(
    plan: ApplyPlan,
    backup_file: bytes,
    executor: AsyncOperationExecutor,
) -> ApplyReport:
    report = ApplyReport(backup_file=backup_file)

    for operation in plan.operations:
        try:
            await executor.execute(operation)
        except SkipOperationError as exc:
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

    return report
