"""Tests for the super-admin seed.

The seed creates exactly one row: jsanchez@tradingsolutions.com as compliance.
All other users must be created through the admin panel UI.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text


MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"
SUPER_ADMIN_EMAIL = "jsanchez@tradingsolutions.com"


class TestSeedSuperAdminFile:
    """The seed SQL file must exist and contain the expected single row."""

    @pytest.fixture
    def seed_sql(self):
        path = MIGRATIONS_DIR / "seed_super_admin.sql"
        assert path.exists(), f"Seed file not found: {path}"
        return path.read_text()

    def test_seed_includes_super_admin(self, seed_sql):
        assert SUPER_ADMIN_EMAIL in seed_sql
        assert "compliance" in seed_sql

    def test_seed_uses_on_conflict_for_idempotency(self, seed_sql):
        # Postgres idempotency: ON CONFLICT ... DO UPDATE or DO NOTHING
        assert "ON CONFLICT" in seed_sql, "Seed must be idempotent"

    def test_seed_only_creates_one_user(self, seed_sql):
        # Count INSERT statements that target the users table.
        # Should be exactly one (the super admin).
        lowered = seed_sql.lower()
        # Naive but effective: count 'insert into users'
        assert lowered.count("insert into users") == 1


class TestSeedApplicationIdempotent:
    """Apply the seed twice against SQLite and verify it does not duplicate."""

    def _apply_seed_to_sqlite(self, db_session):
        """Port the Postgres seed to SQLite-compatible syntax for testing."""
        db_session.execute(text("""
            INSERT INTO users (email, nombre_display, rol, activo)
            VALUES (:email, 'Juan Sanchez', 'compliance', 1)
            ON CONFLICT(email) DO UPDATE SET
                nombre_display = excluded.nombre_display,
                rol = excluded.rol,
                activo = excluded.activo
        """), {"email": SUPER_ADMIN_EMAIL})
        db_session.commit()

    def test_seed_creates_super_admin(self, db_session):
        self._apply_seed_to_sqlite(db_session)
        row = db_session.execute(
            text("SELECT email, nombre_display, rol, activo FROM users WHERE email=:e"),
            {"e": SUPER_ADMIN_EMAIL},
        ).fetchone()
        assert row is not None
        assert row[0] == SUPER_ADMIN_EMAIL
        assert row[2] == "compliance"
        assert bool(row[3]) is True

    def test_seed_is_idempotent(self, db_session):
        self._apply_seed_to_sqlite(db_session)
        self._apply_seed_to_sqlite(db_session)
        count = db_session.execute(text("SELECT COUNT(*) FROM users")).scalar()
        assert count == 1

    def test_seed_does_not_create_other_users(self, db_session):
        self._apply_seed_to_sqlite(db_session)
        rows = db_session.execute(text("SELECT email FROM users")).fetchall()
        assert [r[0] for r in rows] == [SUPER_ADMIN_EMAIL]
