"""Reminder dispatcher.

Called on app page-load (gated by a 5-minute session_state timer in app.py)
and from scripts/send_reminders.py for manual/cron runs.

Workflow:
1. Disable any reminders past their expires_at.
2. Find all due reminders (enabled, next_reminder_at <= NOW(), not expired).
3. For each due: insert in-app notifications for the request owner AND
   the submitter (if different); advance next_reminder_at by frequency_days.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database.crud.reminders import (
    disable_expired_reminders,
    get_due_reminders,
    advance_reminder,
)
from database.crud.documents import insert_notification
from services.logging_config import get_logger
from utils.timezone import utc_now

logger = get_logger(__name__)


def process_due_reminders(session: Session, current_user_email: Optional[str] = None) -> int:
    """Fire notifications for all due reminders and advance their next-fire time.

    Idempotent: calling twice within the same minute does not produce
    duplicates because advance_reminder pushes next_reminder_at forward by
    frequency_days, so the second call won't see the same row as due.

    Returns the number of due reminders processed (for logging/metrics).
    """
    now = utc_now()
    try:
        disable_expired_reminders(session, now=now)
    except Exception:
        logger.exception("Failed to disable expired reminders")

    try:
        due = get_due_reminders(session, now=now)
    except Exception:
        logger.exception("Failed to fetch due reminders")
        return 0

    processed = 0
    for r in due:
        recipients = set()
        if r.get("user_email"):
            recipients.add(r["user_email"])
        if r.get("submitted_by_email"):
            recipients.add(r["submitted_by_email"])

        case_id = r.get("case_id") or f"#{r['request_id']}"
        company = r.get("company_name") or "(sin nombre)"
        message = (
            f"Recordatorio: solicitud {case_id} ({company}) está pendiente "
            f"de documentación."
        )

        for email in recipients:
            if not email:
                continue
            try:
                insert_notification(
                    session,
                    user_email=email,
                    request_id=r["request_id"],
                    message=message,
                )
            except Exception:
                logger.exception("Failed to insert reminder notification", extra={"to": email})

        # Advance next_reminder_at = now + frequency_days
        try:
            new_next = now + timedelta(days=r["frequency_days"])
            advance_reminder(session, schedule_id=r["id"], new_next_at=new_next)
        except Exception:
            logger.exception("Failed to advance reminder", extra={"sched_id": r["id"]})

        processed += 1

    return processed
