"""Tests for migration 003: users, inside_sales_comerciales, request_attachments, reminder_schedule + new columns on requests.

Uses the SQLite conftest fixture. The conftest DDL must stay in sync with
the Postgres migration 003 SQL so local tests mirror production schema.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Tables exist in conftest DDL (SQLite test fixture)
# ---------------------------------------------------------------------------

def _table_exists(session, table_name: str) -> bool:
    row = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": table_name},
    ).fetchone()
    return row is not None


def _column_exists(session, table: str, column: str) -> bool:
    rows = session.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


class TestMigration003TablesExist:
    """Verify the new tables from migration 003 are present in the test schema."""

    def test_users_table_exists(self, db_session):
        assert _table_exists(db_session, "users")

    def test_inside_sales_comerciales_table_exists(self, db_session):
        assert _table_exists(db_session, "inside_sales_comerciales")

    def test_request_attachments_table_exists(self, db_session):
        assert _table_exists(db_session, "request_attachments")

    def test_reminder_schedule_table_exists(self, db_session):
        assert _table_exists(db_session, "reminder_schedule")


class TestMigration003NewColumns:
    """Verify new columns on requests table."""

    @pytest.mark.parametrize("column", [
        "submitted_by_email",
        "notes",
        "case_id",
        "reminder_max_months",
    ])
    def test_requests_has_new_column(self, db_session, column):
        assert _column_exists(db_session, "requests", column), f"Missing column requests.{column}"


class TestUsersSchema:
    def test_insert_user_minimal(self, db_session):
        db_session.execute(text("""
            INSERT INTO users (email, nombre_display, rol, activo)
            VALUES ('test@tradingsolutions.com', 'Test User', 'comercial', 1)
        """))
        db_session.commit()
        row = db_session.execute(
            text("SELECT email, nombre_display, rol, activo FROM users WHERE email='test@tradingsolutions.com'")
        ).fetchone()
        assert row is not None
        assert row[0] == "test@tradingsolutions.com"
        assert row[1] == "Test User"
        assert row[2] == "comercial"
        assert bool(row[3]) is True

    def test_email_is_primary_key(self, db_session):
        db_session.execute(text("""
            INSERT INTO users (email, nombre_display, rol, activo)
            VALUES ('dup@tradingsolutions.com', 'First', 'comercial', 1)
        """))
        db_session.commit()
        with pytest.raises(Exception):
            db_session.execute(text("""
                INSERT INTO users (email, nombre_display, rol, activo)
                VALUES ('dup@tradingsolutions.com', 'Second', 'inside_sales', 1)
            """))
            db_session.commit()


class TestInsideSalesComercialesSchema:
    def test_many_to_many_relationship(self, db_session):
        # Two comerciales + one inside sales
        db_session.execute(text("INSERT INTO users (email, nombre_display, rol, activo) VALUES ('is@tradingsolutions.com', 'IS User', 'inside_sales', 1)"))
        db_session.execute(text("INSERT INTO users (email, nombre_display, rol, activo) VALUES ('c1@tradingsolutions.com', 'Comercial 1', 'comercial', 1)"))
        db_session.execute(text("INSERT INTO users (email, nombre_display, rol, activo) VALUES ('c2@tradingsolutions.com', 'Comercial 2', 'comercial', 1)"))
        db_session.commit()

        db_session.execute(text("""
            INSERT INTO inside_sales_comerciales (inside_sales_email, comercial_email, assigned_by)
            VALUES ('is@tradingsolutions.com', 'c1@tradingsolutions.com', 'admin@tradingsolutions.com')
        """))
        db_session.execute(text("""
            INSERT INTO inside_sales_comerciales (inside_sales_email, comercial_email, assigned_by)
            VALUES ('is@tradingsolutions.com', 'c2@tradingsolutions.com', 'admin@tradingsolutions.com')
        """))
        db_session.commit()

        rows = db_session.execute(text("""
            SELECT comercial_email FROM inside_sales_comerciales
            WHERE inside_sales_email = 'is@tradingsolutions.com'
            ORDER BY comercial_email
        """)).fetchall()
        assert [r[0] for r in rows] == ["c1@tradingsolutions.com", "c2@tradingsolutions.com"]

    def test_composite_primary_key_prevents_duplicate_assignment(self, db_session):
        db_session.execute(text("INSERT INTO users (email, nombre_display, rol, activo) VALUES ('is@tradingsolutions.com', 'IS', 'inside_sales', 1)"))
        db_session.execute(text("INSERT INTO users (email, nombre_display, rol, activo) VALUES ('c@tradingsolutions.com', 'C', 'comercial', 1)"))
        db_session.execute(text("""
            INSERT INTO inside_sales_comerciales (inside_sales_email, comercial_email)
            VALUES ('is@tradingsolutions.com', 'c@tradingsolutions.com')
        """))
        db_session.commit()
        with pytest.raises(Exception):
            db_session.execute(text("""
                INSERT INTO inside_sales_comerciales (inside_sales_email, comercial_email)
                VALUES ('is@tradingsolutions.com', 'c@tradingsolutions.com')
            """))
            db_session.commit()


class TestRequestAttachmentsSchema:
    def test_insert_attachment(self, db_session, seed_profiles):
        # Need a request first
        db_session.execute(text("""
            INSERT INTO requests (profile_id, company_name, user_email)
            VALUES (:pid, 'Acme', 'user@tradingsolutions.com')
        """), {"pid": seed_profiles["cliente"]})
        db_session.commit()
        request_id = db_session.execute(text("SELECT id FROM requests LIMIT 1")).scalar()

        db_session.execute(text("""
            INSERT INTO request_attachments (request_id, file_name, drive_link, uploaded_by)
            VALUES (:rid, 'doc.pdf', 'https://drive.google.com/xxx', 'user@tradingsolutions.com')
        """), {"rid": request_id})
        db_session.commit()

        row = db_session.execute(text("SELECT file_name, drive_link, uploaded_by FROM request_attachments WHERE request_id=:rid"), {"rid": request_id}).fetchone()
        assert row is not None
        assert row[0] == "doc.pdf"
        assert row[1] == "https://drive.google.com/xxx"
        assert row[2] == "user@tradingsolutions.com"


class TestReminderScheduleSchema:
    def test_insert_schedule(self, db_session, seed_profiles):
        db_session.execute(text("""
            INSERT INTO requests (profile_id, company_name, user_email)
            VALUES (:pid, 'Acme', 'user@tradingsolutions.com')
        """), {"pid": seed_profiles["cliente"]})
        db_session.commit()
        request_id = db_session.execute(text("SELECT id FROM requests LIMIT 1")).scalar()

        db_session.execute(text("""
            INSERT INTO reminder_schedule (request_id, next_reminder_at, expires_at, enabled, frequency_days)
            VALUES (:rid, '2026-04-21 00:00:00', '2026-05-14 00:00:00', 1, 7)
        """), {"rid": request_id})
        db_session.commit()

        row = db_session.execute(text("SELECT frequency_days, enabled FROM reminder_schedule WHERE request_id=:rid"), {"rid": request_id}).fetchone()
        assert row is not None
        assert row[0] == 7
        assert bool(row[1]) is True


class TestCaseIdBackfill:
    """Backfill SQL in migration is Postgres-specific (LPAD, || concat).
    Here we test the Python equivalent logic that will run in
    database/crud/clientes.py:insert_client_request.
    """

    def test_case_id_format_from_id(self):
        from database.crud.clientes import format_case_id
        assert format_case_id(1) == "C0001"
        assert format_case_id(42) == "C0042"
        assert format_case_id(9999) == "C9999"

    def test_case_id_format_larger_than_9999(self):
        """For MVP we only support up to 9999. If id > 9999, format with more digits."""
        from database.crud.clientes import format_case_id
        # Should still produce a valid case_id even if wider than 4 digits
        result = format_case_id(10000)
        assert result.startswith("C")
        assert result == "C10000"


# ---------------------------------------------------------------------------
# Migration SQL file integrity
# ---------------------------------------------------------------------------

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


class TestMigration003SqlFile:
    """Verify the Postgres migration SQL file exists and has the expected DDL."""

    @pytest.fixture
    def migration_sql(self):
        path = MIGRATIONS_DIR / "003_users_admin_and_enhancements.sql"
        assert path.exists(), f"Migration file not found: {path}"
        return path.read_text()

    def test_creates_users_table(self, migration_sql):
        assert "CREATE TABLE IF NOT EXISTS users" in migration_sql
        assert "email VARCHAR(255) PRIMARY KEY" in migration_sql
        assert "rol VARCHAR(20)" in migration_sql

    def test_creates_inside_sales_comerciales_table(self, migration_sql):
        assert "CREATE TABLE IF NOT EXISTS inside_sales_comerciales" in migration_sql
        assert "PRIMARY KEY (inside_sales_email, comercial_email)" in migration_sql

    def test_creates_request_attachments_table(self, migration_sql):
        assert "CREATE TABLE IF NOT EXISTS request_attachments" in migration_sql
        assert "ON DELETE CASCADE" in migration_sql

    def test_creates_reminder_schedule_table(self, migration_sql):
        assert "CREATE TABLE IF NOT EXISTS reminder_schedule" in migration_sql
        assert "frequency_days" in migration_sql
        assert "expires_at" in migration_sql

    def test_adds_new_columns_to_requests(self, migration_sql):
        for col in ("submitted_by_email", "notes", "case_id", "reminder_max_months"):
            assert f"ADD COLUMN IF NOT EXISTS {col}" in migration_sql, f"Missing ALTER for {col}"

    def test_case_id_backfill_sql_present(self, migration_sql):
        # Postgres uses || for concat and LPAD
        assert "UPDATE requests" in migration_sql
        assert "case_id" in migration_sql
        assert "LPAD" in migration_sql

    def test_python_runner_exists(self):
        path = MIGRATIONS_DIR / "003_users_admin_and_enhancements.py"
        assert path.exists(), f"Runner not found: {path}"
