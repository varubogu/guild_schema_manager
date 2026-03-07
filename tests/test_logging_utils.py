from __future__ import annotations

import asyncio
import logging

import pytest

from bot.logging_utils import log_async_lifecycle


def test_log_async_lifecycle_logs_start_and_end(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("tests.logging.lifecycle")

    @log_async_lifecycle(
        logger,
        "command.schema.apply",
        lambda value: {"user_id": 42, "value": value},
    )
    async def _work(value: int) -> int:
        return value + 1

    caplog.set_level(logging.INFO, logger="tests.logging.lifecycle")
    result = asyncio.run(_work(10))

    assert result == 11
    assert "command.schema.apply.start user_id=42 value=10" in caplog.text
    assert "command.schema.apply.end status=ok" in caplog.text


def test_log_async_lifecycle_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("tests.logging.lifecycle.error")

    @log_async_lifecycle(logger, "event.on_ready")
    async def _fail() -> None:
        raise RuntimeError("boom")

    caplog.set_level(logging.INFO, logger="tests.logging.lifecycle.error")
    with pytest.raises(RuntimeError):
        asyncio.run(_fail())

    assert "event.on_ready.start" in caplog.text
    assert "event.on_ready.end status=error" in caplog.text
