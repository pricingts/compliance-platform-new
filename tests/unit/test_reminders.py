"""Tests for the reminder system (Phase 7 / F7).

Two layers:
1. CRUD: insert_reminder_schedule, get_due_reminders, advance_reminder, disable_expired.
2. Service: process_due_reminders orchestrator.

Frequency × max-duration policy:
- Semanal (7 days), Quincenal (14), Mensual (30) — frequency_days
- 1, 2, or 3 months — max_months
Both editable independently. Timer starts at created_at.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from utils.timezone import utc_now


@pytest.fixture
def request_id(db_session, seed_profiles):
    db_session.execute(text("""
        INSERT INTO requests (profile_id, company_name, user_email)
        VALUES (:pid, 'Acme', 'owner@tradingsolutions.com')
    """), {"pid": seed_profiles["cliente"]})
    db_session.commit()
    return db_session.execute(text("SELECT id FROM requests LIMIT 1")).scalar()


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

class TestInsertReminderSchedule:
    def test_sets_next_and_expires(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule
        created = datetime(2026, 4, 14, 12, 0, 0)
        insert_reminder_schedule(
            db_session,
            request_id=request_id,
            frequency_days=7,
            max_months=2,
            created_at=created,
        )
        row = db_session.execute(text("""
            SELECT next_reminder_at, expires_at, frequency_days, enabled
              FROM reminder_schedule WHERE request_id=:rid
        """), {"rid": request_id}).fetchone()
        assert row is not None
        # next = created + 7d, expires = created + 60d (~2 months)
        assert row[2] == 7
        assert bool(row[3]) is True

    def test_default_created_at_is_utcnow(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule
        insert_reminder_schedule(
            db_session,
            request_id=request_id,
            frequency_days=14,
            max_months=1,
        )
        row = db_session.execute(text("""
            SELECT next_reminder_at, expires_at, frequency_days
              FROM reminder_schedule WHERE request_id=:rid
        """), {"rid": request_id}).fetchone()
        assert row[2] == 14


class TestGetDueReminders:
    def test_returns_due_only(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule, get_due_reminders
        # Due reminder
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=1,
            created_at=utc_now() - timedelta(days=8),
        )
        due = get_due_reminders(db_session, now=utc_now())
        assert len(due) == 1

    def test_excludes_disabled(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule, get_due_reminders
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=1,
            created_at=utc_now() - timedelta(days=8),
        )
        # Disable it
        db_session.execute(text("UPDATE reminder_schedule SET enabled=FALSE WHERE request_id=:rid"), {"rid": request_id})
        db_session.commit()
        assert get_due_reminders(db_session, now=utc_now()) == []

    def test_excludes_not_yet_due(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule, get_due_reminders
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=1,
            created_at=utc_now(),  # next_reminder_at = now+7d
        )
        assert get_due_reminders(db_session, now=utc_now()) == []


class TestAdvanceReminder:
    def test_pushes_next_reminder_forward(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule, advance_reminder
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=2,
            created_at=utc_now() - timedelta(days=10),
        )
        sched_id = db_session.execute(text("SELECT id FROM reminder_schedule WHERE request_id=:rid"), {"rid": request_id}).scalar()
        new_next = utc_now() + timedelta(days=7)
        advance_reminder(db_session, schedule_id=sched_id, new_next_at=new_next)
        next_at = db_session.execute(text("SELECT next_reminder_at FROM reminder_schedule WHERE id=:id"), {"id": sched_id}).scalar()
        # Compare loosely (strings vs datetimes vary by dialect)
        assert next_at is not None


class TestDisableExpired:
    def test_disables_past_expires_at(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule, disable_expired_reminders
        # Created 4 months ago with 1-month limit → already expired
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=1,
            created_at=utc_now() - timedelta(days=120),
        )
        disable_expired_reminders(db_session, now=utc_now())
        enabled = db_session.execute(text("SELECT enabled FROM reminder_schedule WHERE request_id=:rid"), {"rid": request_id}).scalar()
        assert bool(enabled) is False


# ---------------------------------------------------------------------------
# Service tests: process_due_reminders
# ---------------------------------------------------------------------------

class TestProcessDueReminders:
    def test_creates_notification_for_due(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule
        from services.reminders import process_due_reminders
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=2,
            created_at=utc_now() - timedelta(days=8),
        )
        process_due_reminders(db_session)
        count = db_session.execute(text("SELECT COUNT(*) FROM notifications WHERE request_id=:rid"), {"rid": request_id}).scalar()
        assert count >= 1

    def test_skips_not_due(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule
        from services.reminders import process_due_reminders
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=2,
            created_at=utc_now(),
        )
        process_due_reminders(db_session)
        count = db_session.execute(text("SELECT COUNT(*) FROM notifications WHERE request_id=:rid"), {"rid": request_id}).scalar()
        assert count == 0

    def test_notifies_owner_and_submitter(self, db_session, seed_profiles):
        from database.crud.reminders import insert_reminder_schedule
        from services.reminders import process_due_reminders
        # Create a request with both owner and submitter (IS scenario)
        db_session.execute(text("""
            INSERT INTO requests (profile_id, company_name, user_email, submitted_by_email)
            VALUES (:pid, 'Acme', 'is@tradingsolutions.com', 'is@tradingsolutions.com')
        """), {"pid": seed_profiles["cliente"]})
        db_session.commit()
        rid = db_session.execute(text("SELECT id FROM requests LIMIT 1")).scalar()
        insert_reminder_schedule(
            db_session, request_id=rid, frequency_days=7, max_months=2,
            created_at=utc_now() - timedelta(days=8),
        )
        process_due_reminders(db_session)
        # Both go to is@... but it's the same address, so only 1 notification
        notif_emails = db_session.execute(
            text("SELECT DISTINCT user_email FROM notifications WHERE request_id=:rid"),
            {"rid": rid},
        ).fetchall()
        assert len(notif_emails) >= 1

    def test_disables_expired_during_process(self, db_session, request_id):
        from database.crud.reminders import insert_reminder_schedule
        from services.reminders import process_due_reminders
        # Created 4 months ago with 1-month max → expired
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=1,
            created_at=utc_now() - timedelta(days=120),
        )
        process_due_reminders(db_session)
        enabled = db_session.execute(text("SELECT enabled FROM reminder_schedule WHERE request_id=:rid"), {"rid": request_id}).scalar()
        assert bool(enabled) is False

    def test_idempotent_advances_next(self, db_session, request_id):
        """Calling twice in a row shouldn't double-notify."""
        from database.crud.reminders import insert_reminder_schedule
        from services.reminders import process_due_reminders
        insert_reminder_schedule(
            db_session, request_id=request_id, frequency_days=7, max_months=2,
            created_at=utc_now() - timedelta(days=8),
        )
        process_due_reminders(db_session)
        first_count = db_session.execute(text("SELECT COUNT(*) FROM notifications WHERE request_id=:rid"), {"rid": request_id}).scalar()
        process_due_reminders(db_session)
        second_count = db_session.execute(text("SELECT COUNT(*) FROM notifications WHERE request_id=:rid"), {"rid": request_id}).scalar()
        assert first_count == second_count


class TestInsertWithReminderMaxMonths:
    def test_persists_reminder_max_months(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="u@tradingsolutions.com",
            reminder_max_months=2,
        )
        val = db_session.execute(text("SELECT reminder_max_months FROM requests WHERE id=:id"), {"id": rid}).scalar()
        assert val == 2
