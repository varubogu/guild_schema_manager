from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


def log_async_lifecycle(
    logger: logging.Logger,
    action: str,
    context_builder: Callable[P, dict[str, Any]] | None = None,
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    def decorator(
        func: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            context = (
                context_builder(*args, **kwargs) if context_builder is not None else {}
            )
            context_text = _format_context(context)
            suffix = f" {context_text}" if context_text else ""

            started = time.perf_counter()
            logger.info("%s.start%s", action, suffix)
            try:
                result = await func(*args, **kwargs)
            except Exception:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.exception(
                    "%s.end status=error elapsed_ms=%d%s", action, elapsed_ms, suffix
                )
                raise

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("%s.end status=ok elapsed_ms=%d%s", action, elapsed_ms, suffix)
            return result

        return wrapper

    return decorator


def _format_context(context: dict[str, Any]) -> str:
    if not context:
        return ""

    parts: list[str] = []
    for key in sorted(context):
        value = context[key]
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts)
