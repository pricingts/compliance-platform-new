"""Tests for migration 007: drop NOT NULL on registration.doc_type_id.

Production bug (2026-04-20): upload form crashed with
    psycopg2.errors.NotNullViolation: null value in column "doc_type_id"
    of relation "registration" violates not-null constraint

Root cause: production Postgres schema diverged from init_db.sql, which
declares ``doc_type_id`` as nullable. The platform's ``upsert_request_info``
CRUD relies on that nullability to insert a placeholder row for
request-level metadata (``razon_social`` / ``fecha_creacion``) before any
actual documents exist.

This migration realigns production with the intended schema by dropping
the NOT NULL constraint.
"""
from __future__ import annotations

from pathlib import Path

import pytest


MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


class TestMigration007SqlFile:
    """Verify the migration SQL file exists and has the expected DDL."""

    @pytest.fixture
    def migration_path(self):
        path = MIGRATIONS_DIR / "007_registration_doc_type_nullable.sql"
        return path

    @pytest.fixture
    def migration_sql(self, migration_path):
        assert migration_path.exists(), (
            f"Migration file not found: {migration_path}"
        )
        return migration_path.read_text()

    def test_migration_file_exists(self, migration_path):
        assert migration_path.exists(), (
            f"Migration file must exist at {migration_path}"
        )

    def test_targets_registration_table(self, migration_sql):
        assert "ALTER TABLE registration" in migration_sql

    def test_drops_not_null_on_doc_type_id(self, migration_sql):
        # The canonical Postgres way to relax a NOT NULL constraint.
        assert "ALTER COLUMN doc_type_id DROP NOT NULL" in migration_sql

    def test_is_idempotent(self, migration_sql):
        """Migration must be safe to re-run.

        ``DROP NOT NULL`` on a column that is already nullable is a no-op
        in Postgres, so the statement itself is idempotent. We still
        require an explicit guard comment to signal intent.
        """
        assert "idempotent" in migration_sql.lower()


class TestInitDbSchemaStillNullable:
    """Guard rail: init_db.sql must keep ``doc_type_id`` nullable.

    If someone regenerates init_db.sql from a snapshot of the (now-fixed)
    production schema or mistakenly adds NOT NULL back, this test catches
    the regression before it reaches production again.
    """

    def test_doc_type_id_not_declared_not_null_in_init_db(self):
        init_db = Path(__file__).parent.parent.parent / "init_db.sql"
        sql = init_db.read_text()

        # Locate the registration CREATE TABLE block
        marker = "CREATE TABLE registration"
        start = sql.find(marker)
        assert start != -1, "registration table missing from init_db.sql"
        end = sql.find(");", start)
        block = sql[start:end]

        # ``doc_type_id`` line must not say NOT NULL
        lines = [ln.strip() for ln in block.splitlines() if "doc_type_id" in ln]
        assert lines, "doc_type_id column not found in registration table"
        for line in lines:
            assert "NOT NULL" not in line.upper(), (
                f"registration.doc_type_id must remain nullable (line: {line!r})"
            )
