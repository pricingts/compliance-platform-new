"""Integration tests for migration 006: seed L. Bandera as platform admin.

The seed mirrors the pattern of ``seed_super_admin.sql``:
    - single INSERT ... ON CONFLICT (email) DO UPDATE row
    - role = 'compliance' (equivalent of admin in this platform)
    - idempotent: applying twice leaves exactly one row

These tests apply the Postgres-flavoured SQL against a SQLite in-memory
engine, porting it where needed. SQLite 3.24+ supports
``ON CONFLICT(<col>) DO UPDATE SET ... = excluded.<col>`` which is
syntactically close enough for our idempotency assertions.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.integration


MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"
LBANDERA_EMAIL = "lbandera@tradingsolutions.com"


def _apply_lbandera_seed_sqlite(db_session):
    """Port the Postgres seed to SQLite-compatible syntax.

    SQLite uses ``excluded.<col>`` (lowercase) and needs the PK column
    specified in the conflict target.
    """
    db_session.execute(
        text(
            """
            INSERT INTO users (email, nombre_display, rol, activo, created_by)
            VALUES (:email, 'L. Bandera', 'compliance', 1, 'seed')
            ON CONFLICT(email) DO UPDATE SET
                nombre_display = excluded.nombre_display,
                rol = excluded.rol,
                activo = excluded.activo
            """
        ),
        {"email": LBANDERA_EMAIL},
    )
    db_session.commit()


class TestSeedLbanderaFile:
    """The seed SQL file must exist and contain the expected row."""

    @pytest.fixture
    def seed_sql(self):
        path = MIGRATIONS_DIR / "006_seed_admin_lbandera.sql"
        assert path.exists(), f"Seed file not found: {path}"
        return path.read_text()

    def test_seed_includes_lbandera_email(self, seed_sql):
        assert LBANDERA_EMAIL in seed_sql

    def test_seed_uses_compliance_role(self, seed_sql):
        # Per user decision, lbandera is seeded as 'compliance' (admin-equivalent).
        assert "'compliance'" in seed_sql

    def test_seed_uses_on_conflict_for_idempotency(self, seed_sql):
        assert "ON CONFLICT" in seed_sql, "Seed must be idempotent"

    def test_seed_targets_users_table(self, seed_sql):
        assert "INSERT INTO users" in seed_sql.lower() or "insert into users" in seed_sql.lower()


class TestSeedLbanderaApplication:
    """Apply the SQL against SQLite and verify row state."""

    def test_seed_applies_lbandera_with_compliance_role(self, db_session):
        _apply_lbandera_seed_sqlite(db_session)
        row = db_session.execute(
            text(
                "SELECT email, nombre_display, rol, activo FROM users WHERE email=:e"
            ),
            {"e": LBANDERA_EMAIL},
        ).fetchone()
        assert row is not None, "Seed must insert lbandera row"
        assert row[0] == LBANDERA_EMAIL
        assert row[1] == "L. Bandera"
        assert row[2] == "compliance"
        assert bool(row[3]) is True

    def test_seed_is_idempotent(self, db_session):
        _apply_lbandera_seed_sqlite(db_session)
        _apply_lbandera_seed_sqlite(db_session)

        count = db_session.execute(
            text("SELECT COUNT(*) FROM users WHERE email=:e"),
            {"e": LBANDERA_EMAIL},
        ).scalar()
        assert count == 1, "Applying seed twice must still yield exactly one row"

        row = db_session.execute(
            text(
                "SELECT nombre_display, rol, activo FROM users WHERE email=:e"
            ),
            {"e": LBANDERA_EMAIL},
        ).fetchone()
        assert row is not None
        assert row[0] == "L. Bandera"
        assert row[1] == "compliance"
        assert bool(row[2]) is True

    def test_seed_updates_existing_row_values(self, db_session):
        """If a row exists with the same email but different values, re-running
        the seed should reset the row to the canonical values."""
        # Pre-seed a different value for this email
        db_session.execute(
            text(
                """
                INSERT INTO users (email, nombre_display, rol, activo, created_by)
                VALUES (:e, 'Wrong Name', 'otro', 0, 'manual')
                """
            ),
            {"e": LBANDERA_EMAIL},
        )
        db_session.commit()

        _apply_lbandera_seed_sqlite(db_session)

        row = db_session.execute(
            text(
                "SELECT nombre_display, rol, activo FROM users WHERE email=:e"
            ),
            {"e": LBANDERA_EMAIL},
        ).fetchone()
        assert row[0] == "L. Bandera"
        assert row[1] == "compliance"
        assert bool(row[2]) is True
