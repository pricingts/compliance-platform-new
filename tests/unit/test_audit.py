"""Tests for audit trail — schema and service."""
from sqlalchemy import text


class TestAuditLogSchema:
    """Verify audit_log table exists and accepts inserts."""

    def test_audit_log_table_exists(self, db_session):
        """The audit_log table should exist in the test schema."""
        result = db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
        ).fetchone()
        assert result is not None, "audit_log table must exist"

    def test_audit_log_insert_and_read(self, db_session):
        """log_action should persist a row to audit_log."""
        from services.audit import log_action

        log_action(
            session=db_session,
            user_email="test@tradingsolutions.com",
            action="CREATE",
            entity_type="request",
            entity_id=1,
            new_value={"company_name": "Test Corp"},
            details="Created via test",
        )
        db_session.commit()

        row = db_session.execute(
            text("SELECT user_email, action, entity_type, entity_id, new_value, details FROM audit_log")
        ).fetchone()
        assert row is not None
        assert row[0] == "test@tradingsolutions.com"
        assert row[1] == "CREATE"
        assert row[2] == "request"
        assert row[3] == 1
        assert "Test Corp" in row[4]
        assert row[5] == "Created via test"

    def test_audit_log_nullable_fields(self, db_session):
        """entity_id, old_value, new_value, details should accept NULL."""
        from services.audit import log_action

        log_action(
            session=db_session,
            user_email="test@tradingsolutions.com",
            action="LOGIN",
            entity_type="session",
        )
        db_session.commit()

        row = db_session.execute(
            text("SELECT entity_id, old_value, new_value, details FROM audit_log")
        ).fetchone()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None
        assert row[3] is None
