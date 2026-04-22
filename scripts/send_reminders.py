"""Manually dispatch due reminders.

Use this from cron or as a Railway one-off when no user opens the app for
a while:

    railway run python scripts/send_reminders.py

Equivalent to the on-page-load trigger in app.py but driven from the CLI.
"""
from __future__ import annotations

import sys

from services.logging_config import get_logger

logger = get_logger(__name__)


def main() -> int:
    from database.db import SessionLocal
    from services.reminders import process_due_reminders

    session = SessionLocal()
    try:
        n = process_due_reminders(session)
        logger.info("Reminders processed: %s", n)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
