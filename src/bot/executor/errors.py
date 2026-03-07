from __future__ import annotations


class SkipOperationError(RuntimeError):
    """Raised when an operation should be reported as skipped, not failed."""

