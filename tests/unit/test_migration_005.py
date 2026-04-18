"""Tests for migration 005: adds ``email_notified_at`` column on requests.

The column is used by services/mailer to enforce idempotency for the
"request-created" email notification (skip send if already notified).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text


MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def _column_exists(session, table: str, column: str) -> bool:
    rows = session.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


class TestMigration005Schema:
    """Verify the conftest DDL includes the new column (test-schema mirror)."""

    def test_requests_has_email_notified_at(self, db_session):
        assert _column_exists(db_session, "requests", "email_notified_at"), (
            "conftest DDL must include requests.email_notified_at after migration 005"
        )

    def test_email_notified_at_is_nullable_timestamp(self, db_session, seed_profiles):
        # Insert a row without the column set -> should succeed and be NULL
        db_session.execute(
            text("""
                INSERT INTO requests (profile_id, company_name, user_email)
                VALUES (:pid, 'Acme', 'user@tradingsolutions.com')
            """),
            {"pid": seed_profiles["cliente"]},
        )
        db_session.commit()
        row = db_session.execute(
            text("SELECT email_notified_at FROM requests LIMIT 1")
        ).fetchone()
        assert row is not None
        assert row[0] is None

    def test_email_notified_at_accepts_timestamp(self, db_session, seed_profiles):
        db_session.execute(
            text("""
                INSERT INTO requests (profile_id, company_name, user_email, email_notified_at)
                VALUES (:pid, 'Acme', 'user@tradingsolutions.com', '2026-04-18 12:00:00')
            """),
            {"pid": seed_profiles["cliente"]},
        )
        db_session.commit()
        row = db_session.execute(
            text("SELECT email_notified_at FROM requests LIMIT 1")
        ).fetchone()
        assert row is not None
        assert row[0] is not None


class TestMigration005SqlFile:
    """Verify the migration SQL file exists and has the expected DDL."""

    @pytest.fixture
    def migration_sql(self):
        path = MIGRATIONS_DIR / "005_email_notifications.sql"
        assert path.exists(), f"Migration file not found: {path}"
        return path.read_text()

    def test_adds_email_notified_at_column(self, migration_sql):
        assert "ADD COLUMN IF NOT EXISTS email_notified_at" in migration_sql

    def test_column_type_is_timestamp(self, migration_sql):
        assert "TIMESTAMP" in migration_sql

    def test_targets_requests_table(self, migration_sql):
        assert "ALTER TABLE requests" in migration_sql
