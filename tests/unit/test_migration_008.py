"""Tests for migration 007: adds ``email_threads`` table for Gmail threading.

The table stores per-request Gmail threadId + Message-ID chain so subsequent
events (reminders, status changes) thread into the same Gmail conversation.
"""
from __future__ import annotations

from pathlib import Path

import pytest


MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


class TestMigration008SqlFile:
    """Verify the migration SQL file exists and has the expected DDL."""

    @pytest.fixture
    def migration_sql(self):
        path = MIGRATIONS_DIR / "008_email_threads.sql"
        assert path.exists(), f"Migration file not found: {path}"
        return path.read_text()

    def test_file_exists(self):
        path = MIGRATIONS_DIR / "008_email_threads.sql"
        assert path.exists()

    def test_creates_email_threads_table(self, migration_sql):
        assert "CREATE TABLE IF NOT EXISTS email_threads" in migration_sql

    def test_has_foreign_key_to_requests(self, migration_sql):
        # Must reference the requests table via FK (supports cascade delete).
        assert "REFERENCES requests" in migration_sql

    def test_has_at_least_one_index(self, migration_sql):
        assert "CREATE INDEX" in migration_sql

    def test_includes_gmail_thread_id_column(self, migration_sql):
        assert "gmail_thread_id" in migration_sql

    def test_includes_references_chain_column(self, migration_sql):
        assert "references_chain" in migration_sql
