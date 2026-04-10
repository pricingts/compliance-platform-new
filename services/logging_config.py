"""
Structured JSON logging configuration for the compliance platform.

Usage:
    from services.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Request created", extra={"request_id": 123, "user": "jsanchez"})
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON strings with structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include any extra fields passed via the `extra` kwarg
        standard_attrs = {
            "name", "msg", "args", "created", "relativeCreated",
            "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "filename", "module", "pathname", "thread", "threadName",
            "process", "processName", "levelname", "levelno", "message",
            "msecs", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                log_entry[key] = value

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_entry, default=str)


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger configured with structured JSON output.

    The log level is controlled by the LOG_LEVEL environment variable
    (default: INFO). Logs are sent to stderr via StreamHandler for
    Streamlit compatibility.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if get_logger is called multiple times
    if not logger.handlers:
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Prevent log propagation to the root logger to avoid duplicate output
        logger.propagate = False

    return logger
