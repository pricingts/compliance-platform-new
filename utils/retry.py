"""Retry decorator with exponential backoff and optional jitter.

Usage:
    from utils.retry import with_retry

    @with_retry(max_attempts=3, exceptions=(ConnectionError,))
    def flaky_call():
        ...
"""
from __future__ import annotations

import functools
import random
import time
from typing import Any, Callable, Tuple, Type

from services.logging_config import get_logger

logger = get_logger(__name__)


def with_retry(
    max_attempts: int = 3,
    backoff: float = 1.5,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    jitter: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Retry the decorated function up to ``max_attempts`` times on listed
    exceptions, with exponential backoff.

    Args:
        max_attempts: Total attempts (must be >= 1).
        backoff: Base multiplier for the ``backoff * 2**attempt`` delay.
        exceptions: Exception types that trigger a retry. Anything outside this
            tuple propagates immediately.
        jitter: If True, add a random 0-0.3 s jitter to each wait.

    Returns:
        A decorator that wraps the target function.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt >= max_attempts - 1:
                        # No more attempts left — re-raise.
                        raise
                    wait = backoff * (2 ** attempt)
                    if jitter:
                        wait += random.uniform(0, 0.3)
                    logger.warning(
                        "Retry scheduled after exception",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "exception": f"{type(exc).__name__}: {exc}",
                            "next_wait_seconds": wait,
                        },
                    )
                    time.sleep(wait)
            # Defensive: should be unreachable because the loop always returns
            # or raises. Keeps mypy / static analyzers happy.
            if last_exc is not None:  # pragma: no cover
                raise last_exc
            raise RuntimeError("with_retry: unreachable state")  # pragma: no cover

        return wrapper

    return decorator
