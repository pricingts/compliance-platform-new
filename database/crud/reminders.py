"""CRUD for reminder_schedule.

Reminders fire on a frequency cycle (Semanal/Quincenal/Mensual) until the
max-duration cap is reached (1/2/3 months from creation). The two values are
configured independently in the request form.

The orchestrator that emits notifications lives in services/reminders.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from utils.timezone import utc_now


def insert_reminder_schedule(
    session: Session,
    request_id: int,
    frequency_days: int,
    max_months: int,
    created_at: Optional[datetime] = None,
) -> Optional[int]:
    """Create the schedule row for a brand-new request.

    next_reminder_at = created + frequency_days
    expires_at       = created + max_months * 30 days
    """
    created = created_at or utc_now()
    next_at = created + timedelta(days=frequency_days)
    expires_at = created + timedelta(days=max_months * 30)

    dialect = session.bind.dialect.name if session.bind else "unknown"
    params = {
        "request_id": request_id,
        "next_at": next_at,
        "expires_at": expires_at,
        "frequency_days": frequency_days,
    }
    if dialect == "postgresql":
        sched_id = session.execute(
            text("""
                INSERT INTO reminder_schedule
                  (request_id, next_reminder_at, expires_at, enabled, frequency_days)
                VALUES (:request_id, :next_at, :expires_at, TRUE, :frequency_days)
                RETURNING id
            """),
            params,
        ).scalar()
    else:
        # SQLite branch: TRUE literal is supported since 3.23 (we ship 3.49+)
        # but we still need a separate INSERT/SELECT pair because SQLite has
        # no RETURNING clause in older drivers and last_insert_rowid is the
        # canonical way to fetch the new id.
        session.execute(
            text("""
                INSERT INTO reminder_schedule
                  (request_id, next_reminder_at, expires_at, enabled, frequency_days)
                VALUES (:request_id, :next_at, :expires_at, TRUE, :frequency_days)
            """),
            params,
        )
        sched_id = session.execute(
            text("SELECT id FROM reminder_schedule WHERE rowid = last_insert_rowid()")
        ).scalar()
    session.commit()
    return sched_id


def get_due_reminders(session: Session, now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Return reminders that are enabled, not expired, and whose next_reminder_at has passed."""
    cutoff = now or utc_now()
    rows = session.execute(
        text("""
            SELECT rs.id, rs.request_id, rs.frequency_days,
                   rs.next_reminder_at, rs.expires_at,
                   r.case_id, r.company_name, r.user_email, r.submitted_by_email
              FROM reminder_schedule rs
              JOIN requests r ON r.id = rs.request_id
             WHERE rs.enabled = TRUE
               AND rs.next_reminder_at <= :cutoff
               AND rs.expires_at > :cutoff
        """),
        {"cutoff": cutoff},
    ).fetchall()
    return [
        {
            "id": r[0],
            "request_id": r[1],
            "frequency_days": r[2],
            "next_reminder_at": r[3],
            "expires_at": r[4],
            "case_id": r[5],
            "company_name": r[6],
            "user_email": r[7],
            "submitted_by_email": r[8],
        }
        for r in rows
    ]


def advance_reminder(session: Session, schedule_id: int, new_next_at: datetime) -> None:
    """Move the next-fire timestamp forward (typically by frequency_days)."""
    session.execute(
        text("UPDATE reminder_schedule SET next_reminder_at = :next WHERE id = :id"),
        {"next": new_next_at, "id": schedule_id},
    )
    session.commit()


def disable_expired_reminders(session: Session, now: Optional[datetime] = None) -> int:
    """Flip enabled=FALSE for any schedule past its expires_at. Returns rowcount."""
    cutoff = now or utc_now()
    result = session.execute(
        text("""
            UPDATE reminder_schedule
               SET enabled = FALSE
             WHERE enabled = TRUE
               AND expires_at <= :cutoff
        """),
        {"cutoff": cutoff},
    )
    session.commit()
    return result.rowcount or 0
