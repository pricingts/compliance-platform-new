"""Tests for upsert_status function to prevent double writes.

These tests verify that upsert_status creates exactly ONE record per call
and correctly updates existing records without creating duplicates.
The port_registration table (which has a terminal_name field) was affected
by a double-write bug where the upsert logic executed twice.
"""
import pytest
from sqlalchemy import text

from database.crud.documents import upsert_status


# ---------------------------------------------------------------------------
# Helper to insert a request row (required FK for all registration tables)
# ---------------------------------------------------------------------------

def _insert_request(session, profile_id):
    """Insert a minimal request row and return its id."""
    session.execute(
        text(
            "INSERT INTO requests (profile_id, company_name) "
            "VALUES (:pid, :name)"
        ),
        {"pid": profile_id, "name": "Test Company"},
    )
    session.commit()
    row = session.execute(text("SELECT MAX(id) FROM requests")).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUpsertStatus:
    """Verify that upsert_status creates exactly one record per entity."""

    # -- port_registration (has terminal_field) ----------------------------

    def test_port_registration_creates_single_record(
        self, db_session, seed_profiles, seed_statuses
    ):
        """Port registration with terminal should create exactly ONE record, not two."""
        request_id = _insert_request(db_session, seed_profiles["cliente"])
        status_id = seed_statuses["pendiente"]

        upsert_status(
            db_session,
            "port_registration",
            request_id,
            "Puerto Manzanillo",
            status_id,
            terminal_name="Terminal 1",
        )
        db_session.commit()

        count = db_session.execute(
            text("SELECT COUNT(*) FROM port_registration WHERE request_id = :rid"),
            {"rid": request_id},
        ).fetchone()[0]

        assert count == 1, (
            f"Expected exactly 1 port_registration row, got {count} (double-write bug)"
        )

    def test_port_registration_updates_existing(
        self, db_session, seed_profiles, seed_statuses
    ):
        """Updating an existing port registration should not create duplicates."""
        request_id = _insert_request(db_session, seed_profiles["cliente"])
        old_status = seed_statuses["pendiente"]
        new_status = seed_statuses["aprobado"]

        # First insert
        upsert_status(
            db_session,
            "port_registration",
            request_id,
            "Puerto Manzanillo",
            old_status,
            terminal_name="Terminal 1",
        )
        db_session.commit()

        # Update to new status
        upsert_status(
            db_session,
            "port_registration",
            request_id,
            "Puerto Manzanillo",
            new_status,
            terminal_name="Terminal 1",
        )
        db_session.commit()

        count = db_session.execute(
            text("SELECT COUNT(*) FROM port_registration WHERE request_id = :rid"),
            {"rid": request_id},
        ).fetchone()[0]

        assert count == 1, (
            f"Expected 1 row after update, got {count}"
        )

        current_status = db_session.execute(
            text("SELECT status_id FROM port_registration WHERE request_id = :rid"),
            {"rid": request_id},
        ).fetchone()[0]

        assert current_status == new_status, (
            f"Expected status_id={new_status}, got {current_status}"
        )

    def test_port_registration_null_terminal_creates_single_record(
        self, db_session, seed_profiles, seed_statuses
    ):
        """Port registration with NULL terminal should still create exactly one record."""
        request_id = _insert_request(db_session, seed_profiles["cliente"])
        status_id = seed_statuses["pendiente"]

        upsert_status(
            db_session,
            "port_registration",
            request_id,
            "Puerto Lazaro",
            status_id,
            terminal_name=None,
        )
        db_session.commit()

        count = db_session.execute(
            text("SELECT COUNT(*) FROM port_registration WHERE request_id = :rid"),
            {"rid": request_id},
        ).fetchone()[0]

        assert count == 1, (
            f"Expected 1 row with null terminal, got {count}"
        )

    # -- customs_registration (no terminal_field) --------------------------

    def test_customs_registration_creates_single_record(
        self, db_session, seed_profiles, seed_statuses
    ):
        """Customs registration should create exactly one record."""
        request_id = _insert_request(db_session, seed_profiles["cliente"])
        status_id = seed_statuses["pendiente"]

        upsert_status(
            db_session,
            "customs_registration",
            request_id,
            "Aduana Manzanillo",
            status_id,
        )
        db_session.commit()

        count = db_session.execute(
            text("SELECT COUNT(*) FROM customs_registration WHERE request_id = :rid"),
            {"rid": request_id},
        ).fetchone()[0]

        assert count == 1

    # -- shipping_line_registration (no terminal_field) --------------------

    def test_shipping_line_creates_single_record(
        self, db_session, seed_profiles, seed_statuses
    ):
        """Shipping line registration should create exactly one record."""
        request_id = _insert_request(db_session, seed_profiles["cliente"])
        status_id = seed_statuses["pendiente"]

        upsert_status(
            db_session,
            "shipping_line_registration",
            request_id,
            "Maersk",
            status_id,
        )
        db_session.commit()

        count = db_session.execute(
            text(
                "SELECT COUNT(*) FROM shipping_line_registration WHERE request_id = :rid"
            ),
            {"rid": request_id},
        ).fetchone()[0]

        assert count == 1

    # -- internal_registration (no terminal_field) -------------------------

    def test_internal_registration_creates_single_record(
        self, db_session, seed_profiles, seed_statuses
    ):
        """Internal registration should create exactly one record."""
        request_id = _insert_request(db_session, seed_profiles["cliente"])
        status_id = seed_statuses["pendiente"]

        upsert_status(
            db_session,
            "internal_registration",
            request_id,
            "Internal Check",
            status_id,
        )
        db_session.commit()

        count = db_session.execute(
            text(
                "SELECT COUNT(*) FROM internal_registration WHERE request_id = :rid"
            ),
            {"rid": request_id},
        ).fetchone()[0]

        assert count == 1

    # -- error handling ----------------------------------------------------

    def test_invalid_table_raises_error(self, db_session):
        """Invalid table name should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid table name"):
            upsert_status(
                db_session,
                "nonexistent_table",
                1,
                "whatever",
                1,
            )
