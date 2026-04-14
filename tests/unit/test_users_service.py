"""Tests for services/users.py — role resolution and user helpers.

Contract:
- resolve_role reads from users table first; unknown email → 'otro'.
- No fallback to ADMIN_EMAILS — the super-admin must be seeded into users.
- get_active_comerciales returns only rol='comercial' AND activo=TRUE, sorted.
- get_comerciales_for_inside_sales returns only assigned+active comerciales.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture
def seed_users(db_session):
    """Insert a mix of users with different roles and activo states."""
    rows = [
        ("jsanchez@tradingsolutions.com", "Juan Sanchez", "compliance", 1),
        ("pedro@tradingsolutions.com", "Pedro Bruges", "comercial", 1),
        ("andres@tradingsolutions.com", "Andres Consuegra", "comercial", 1),
        ("stephanie@tradingsol.com", "Stephanie Bruges", "comercial", 1),
        ("irina@tradingsolutions.com", "Irina Paternina", "comercial", 0),  # inactive
        ("is1@tradingsolutions.com", "IS User 1", "inside_sales", 1),
        ("is2@tradingsolutions.com", "IS User 2", "inside_sales", 0),  # inactive
    ]
    for email, name, rol, activo in rows:
        db_session.execute(text("""
            INSERT INTO users (email, nombre_display, rol, activo)
            VALUES (:e, :n, :r, :a)
        """), {"e": email, "n": name, "r": rol, "a": activo})
    db_session.commit()
    return rows


class TestResolveRole:
    def test_resolve_role_returns_compliance_for_super_admin(self, db_session, seed_users):
        from services.users import resolve_role
        assert resolve_role(db_session, "jsanchez@tradingsolutions.com") == "compliance"

    def test_resolve_role_returns_comercial(self, db_session, seed_users):
        from services.users import resolve_role
        assert resolve_role(db_session, "pedro@tradingsolutions.com") == "comercial"

    def test_resolve_role_returns_inside_sales(self, db_session, seed_users):
        from services.users import resolve_role
        assert resolve_role(db_session, "is1@tradingsolutions.com") == "inside_sales"

    def test_resolve_role_inactive_returns_otro(self, db_session, seed_users):
        from services.users import resolve_role
        # Irina is comercial but activo=0 → falls through to 'otro'
        assert resolve_role(db_session, "irina@tradingsolutions.com") == "otro"

    def test_resolve_role_inactive_inside_sales_returns_otro(self, db_session, seed_users):
        from services.users import resolve_role
        assert resolve_role(db_session, "is2@tradingsolutions.com") == "otro"

    def test_resolve_role_unknown_returns_otro(self, db_session, seed_users):
        from services.users import resolve_role
        assert resolve_role(db_session, "random@someplace.com") == "otro"

    def test_resolve_role_case_insensitive(self, db_session, seed_users):
        from services.users import resolve_role
        assert resolve_role(db_session, "JSANCHEZ@tradingsolutions.com") == "compliance"
        assert resolve_role(db_session, "Pedro@TradingSolutions.com") == "comercial"

    def test_resolve_role_none_returns_otro(self, db_session, seed_users):
        from services.users import resolve_role
        assert resolve_role(db_session, None) == "otro"
        assert resolve_role(db_session, "") == "otro"


class TestGetUser:
    def test_get_user_returns_dict(self, db_session, seed_users):
        from services.users import get_user
        user = get_user(db_session, "pedro@tradingsolutions.com")
        assert user is not None
        assert user["email"] == "pedro@tradingsolutions.com"
        assert user["nombre_display"] == "Pedro Bruges"
        assert user["rol"] == "comercial"
        assert user["activo"] is True

    def test_get_user_inactive_still_returned(self, db_session, seed_users):
        from services.users import get_user
        user = get_user(db_session, "irina@tradingsolutions.com")
        assert user is not None
        assert user["activo"] is False

    def test_get_user_unknown_returns_none(self, db_session, seed_users):
        from services.users import get_user
        assert get_user(db_session, "nobody@tradingsolutions.com") is None

    def test_get_user_case_insensitive(self, db_session, seed_users):
        from services.users import get_user
        user = get_user(db_session, "PEDRO@tradingsolutions.com")
        assert user is not None
        assert user["email"] == "pedro@tradingsolutions.com"


class TestGetActiveComerciales:
    def test_excludes_inactive(self, db_session, seed_users):
        from services.users import get_active_comerciales
        comerciales = get_active_comerciales(db_session)
        emails = [c["email"] for c in comerciales]
        assert "irina@tradingsolutions.com" not in emails

    def test_excludes_other_roles(self, db_session, seed_users):
        from services.users import get_active_comerciales
        comerciales = get_active_comerciales(db_session)
        emails = [c["email"] for c in comerciales]
        assert "jsanchez@tradingsolutions.com" not in emails  # compliance
        assert "is1@tradingsolutions.com" not in emails       # inside_sales

    def test_returns_active_comerciales_sorted(self, db_session, seed_users):
        from services.users import get_active_comerciales
        comerciales = get_active_comerciales(db_session)
        names = [c["nombre_display"] for c in comerciales]
        assert names == sorted(names), f"Expected sorted, got {names}"

    def test_returns_expected_count(self, db_session, seed_users):
        from services.users import get_active_comerciales
        comerciales = get_active_comerciales(db_session)
        # 3 active comerciales in seed (Pedro, Andres, Stephanie)
        assert len(comerciales) == 3


class TestGetComercialesForInsideSales:
    @pytest.fixture
    def seed_assignments(self, db_session, seed_users):
        """Assign 2 comerciales to is1; none to is2."""
        db_session.execute(text("""
            INSERT INTO inside_sales_comerciales (inside_sales_email, comercial_email)
            VALUES ('is1@tradingsolutions.com', 'pedro@tradingsolutions.com')
        """))
        db_session.execute(text("""
            INSERT INTO inside_sales_comerciales (inside_sales_email, comercial_email)
            VALUES ('is1@tradingsolutions.com', 'andres@tradingsolutions.com')
        """))
        # Assign inactive comercial to test filtering
        db_session.execute(text("""
            INSERT INTO inside_sales_comerciales (inside_sales_email, comercial_email)
            VALUES ('is1@tradingsolutions.com', 'irina@tradingsolutions.com')
        """))
        db_session.commit()

    def test_returns_only_active_assigned(self, db_session, seed_users, seed_assignments):
        from services.users import get_comerciales_for_inside_sales
        comerciales = get_comerciales_for_inside_sales(db_session, "is1@tradingsolutions.com")
        emails = [c["email"] for c in comerciales]
        # Should exclude inactive Irina
        assert "pedro@tradingsolutions.com" in emails
        assert "andres@tradingsolutions.com" in emails
        assert "irina@tradingsolutions.com" not in emails
        assert len(comerciales) == 2

    def test_is_with_no_assignments_returns_empty(self, db_session, seed_users, seed_assignments):
        from services.users import get_comerciales_for_inside_sales
        comerciales = get_comerciales_for_inside_sales(db_session, "is2@tradingsolutions.com")
        assert comerciales == []

    def test_case_insensitive(self, db_session, seed_users, seed_assignments):
        from services.users import get_comerciales_for_inside_sales
        comerciales = get_comerciales_for_inside_sales(db_session, "IS1@tradingsolutions.com")
        assert len(comerciales) == 2

    def test_unknown_is_returns_empty(self, db_session, seed_users):
        from services.users import get_comerciales_for_inside_sales
        assert get_comerciales_for_inside_sales(db_session, "nobody@tradingsolutions.com") == []


class TestRoleHelpers:
    def test_is_comercial_positive(self, db_session, seed_users):
        from services.users import is_comercial
        assert is_comercial(db_session, "pedro@tradingsolutions.com") is True

    def test_is_comercial_negative(self, db_session, seed_users):
        from services.users import is_comercial
        assert is_comercial(db_session, "jsanchez@tradingsolutions.com") is False
        assert is_comercial(db_session, "irina@tradingsolutions.com") is False  # inactive

    def test_is_inside_sales_positive(self, db_session, seed_users):
        from services.users import is_inside_sales
        assert is_inside_sales(db_session, "is1@tradingsolutions.com") is True

    def test_is_inside_sales_negative(self, db_session, seed_users):
        from services.users import is_inside_sales
        assert is_inside_sales(db_session, "pedro@tradingsolutions.com") is False
