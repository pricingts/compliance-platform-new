"""Tests for services/users.py::get_active_compliance_users.

Contract:
- Returns only users with rol='compliance'.
- Excludes inactive (activo=FALSE) users.
- Returns empty list when no compliance users exist.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture
def seed_mixed_users(db_session):
    """Seed a mix of roles and activo states."""
    rows = [
        ("jsanchez@tradingsolutions.com", "Juan Sanchez", "compliance", 1),
        ("second@tradingsolutions.com", "Second Compliance", "compliance", 1),
        ("pedro@tradingsolutions.com", "Pedro Bruges", "comercial", 1),
        ("inactive_compl@tradingsolutions.com", "Inactive Comp", "compliance", 0),
        ("is1@tradingsolutions.com", "IS User 1", "inside_sales", 1),
    ]
    for email, name, rol, activo in rows:
        db_session.execute(
            text("""
                INSERT INTO users (email, nombre_display, rol, activo)
                VALUES (:e, :n, :r, :a)
            """),
            {"e": email, "n": name, "r": rol, "a": activo},
        )
    db_session.commit()
    return rows


class TestGetActiveComplianceUsers:
    def test_returns_only_compliance_users(self, db_session, seed_mixed_users):
        from services.users import get_active_compliance_users

        users = get_active_compliance_users(db_session)
        for u in users:
            assert u["rol"] == "compliance"
        emails = [u["email"] for u in users]
        assert "pedro@tradingsolutions.com" not in emails
        assert "is1@tradingsolutions.com" not in emails

    def test_excludes_inactive_users(self, db_session, seed_mixed_users):
        from services.users import get_active_compliance_users

        users = get_active_compliance_users(db_session)
        emails = [u["email"] for u in users]
        assert "inactive_compl@tradingsolutions.com" not in emails
        # 2 active compliance users
        assert len(users) == 2

    def test_returns_empty_list_when_no_compliance_users(self, db_session):
        from services.users import get_active_compliance_users

        # Only a single comercial in DB — no compliance rows at all.
        db_session.execute(
            text("""
                INSERT INTO users (email, nombre_display, rol, activo)
                VALUES ('p@tradingsolutions.com', 'P', 'comercial', 1)
            """)
        )
        db_session.commit()

        users = get_active_compliance_users(db_session)
        assert users == []
