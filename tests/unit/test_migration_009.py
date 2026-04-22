"""Structural tests for migrations/009_seed_comerciales.sql.

Verifies the SQL file exists, targets the users table, seeds the full
roster with rol='comercial', and is idempotent (ON CONFLICT DO UPDATE).
"""
from __future__ import annotations

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "009_seed_comerciales.sql"
)


def test_migration_009_file_exists():
    assert MIGRATION_PATH.exists(), f"missing {MIGRATION_PATH}"


def test_migration_009_inserts_into_users():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "INSERT INTO users" in sql


def test_migration_009_contains_all_expected_emails():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    expected_emails = [
        "sales@tradingsolutions.com",
        "sales2@tradingsolutions.com",
        "sales3@tradingsolutions.com",
        "sales4@tradingsolutions.com",
        "sales5@tradingsolutions.com",
    ]
    for email in expected_emails:
        assert email in sql, f"missing {email} in 008"


def test_migration_009_rol_is_comercial():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "'comercial'" in sql
    # And does not seed anyone with a different rol.
    assert "'compliance'" not in sql
    assert "'inside_sales'" not in sql


def test_migration_009_is_idempotent():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ON CONFLICT" in sql
    assert "DO UPDATE" in sql
