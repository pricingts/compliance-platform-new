"""Logging decorators for standardized exception handling.

Usage:
    from utils.logging_decorators import log_errors

    @log_errors()
    def do_work(...):
        ...

    @log_errors(reraise=False)
    def best_effort(...):
        ...
"""
from __future__ import annotations

import functools
from typing import Any, Callable, Optional

from services.logging_config import get_logger
from utils.exceptions import ComplianceError

logger = get_logger(__name__)


def log_errors(
    reraise: bool = True,
    user_message: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a function so uncaught exceptions are logged with ``logger.exception``.

    Args:
        reraise: When True (default), re-raise after logging. When False,
            swallow and return ``None``.
        user_message: Optional message. When provided and ``reraise=True``, the
            raised exception's message is replaced with ``user_message``:
              - If the original exception is a :class:`ComplianceError`, the
                same subclass is re-raised with the new message.
              - Otherwise a ``RuntimeError`` is raised with ``user_message``,
                chained ``from`` the original exception.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                # args_hash is a stable but non-sensitive fingerprint.
                try:
                    args_hash = hash((tuple(repr(a) for a in args), tuple(sorted(kwargs.items()))))
                except Exception:
                    args_hash = None
                logger.exception(
                    "Unhandled exception in %s",
                    func.__name__,
                    extra={
                        "function": func.__name__,
                        "args_hash": args_hash,
                        "exception_type": type(exc).__name__,
                    },
                )
                if not reraise:
                    return None
                if user_message is not None:
                    if isinstance(exc, ComplianceError):
                        # Re-raise the SAME subclass with the user-facing message,
                        # chained from the original.
                        raise type(exc)(user_message) from exc
                    raise RuntimeError(user_message) from exc
                raise

        return wrapper

    return decorator
