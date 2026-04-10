"""Tests for audit trail functionality."""
import pytest
import json
from sqlalchemy import text

class TestAuditLog:
    def test_log_action_creates_record(self, db_session):
        """log_action should create an audit_log record."""
        from services.audit import log_action
        log_action(db_session, "test@example.com", "CREATE", "request", 1, details="Test")
        result = db_session.execute(text("SELECT * FROM audit_log")).fetchall()
        assert len(result) == 1
        assert result[0].user_email == "test@example.com"
        assert result[0].action == "CREATE"

    def test_log_action_with_old_new_values(self, db_session):
        """log_action should store old and new values as JSON."""
        from services.audit import log_action
        old = {"status": "pending"}
        new = {"status": "approved"}
        log_action(db_session, "user@test.com", "STATUS_CHANGE", "customs", 5,
                   old_value=old, new_value=new)
        result = db_session.execute(text("SELECT old_value, new_value FROM audit_log")).fetchone()
        assert json.loads(result[0]) == old
        assert json.loads(result[1]) == new

    def test_log_action_without_entity_id(self, db_session):
        """log_action should work without entity_id."""
        from services.audit import log_action
        log_action(db_session, "user@test.com", "UPLOAD", "registration")
        result = db_session.execute(text("SELECT entity_id FROM audit_log")).fetchone()
        assert result[0] is None

    def test_multiple_audit_entries(self, db_session):
        """Multiple actions should create multiple records."""
        from services.audit import log_action
        log_action(db_session, "user1@test.com", "CREATE", "request", 1)
        log_action(db_session, "user2@test.com", "UPDATE", "request", 1)
        log_action(db_session, "user1@test.com", "UPLOAD", "registration", 10)
        count = db_session.execute(text("SELECT COUNT(*) FROM audit_log")).scalar()
        assert count == 3
