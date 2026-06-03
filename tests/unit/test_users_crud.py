"""Tests for database/crud/users.py — CRUD for the users table.

Covers both user CRUD and inside_sales_comerciales assignment CRUD.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


class TestInsertUser:
    def test_insert_and_fetch_user(self, db_session):
        from database.crud.users import insert_user, get_user_by_email
        insert_user(
            db_session,
            email="new@tradingsolutions.com",
            nombre_display="New Comercial",
            rol="comercial",
            created_by="admin@tradingsolutions.com",
        )
        user = get_user_by_email(db_session, "new@tradingsolutions.com")
        assert user is not None
        assert user["nombre_display"] == "New Comercial"
        assert user["rol"] == "comercial"
        assert user["activo"] is True

    def test_insert_user_duplicate_raises(self, db_session):
        from database.crud.users import insert_user
        insert_user(db_session, email="x@tradingsolutions.com", nombre_display="X", rol="comercial")
        with pytest.raises(Exception):
            insert_user(db_session, email="x@tradingsolutions.com", nombre_display="Y", rol="inside_sales")

    def test_create_user_if_absent_inserts_then_reports_existing(self, db_session):
        """Race-safe creation for the admin panel: returns True when it creates
        the user and False (no exception) when the email already exists —
        closing the TOCTOU gap between the pre-check and the insert."""
        from database.crud.users import create_user_if_absent, get_user_by_email

        created = create_user_if_absent(
            db_session,
            email="new@tradingsolutions.com",
            nombre_display="New",
            rol="comercial",
            created_by="admin@tradingsolutions.com",
        )
        assert created is True
        assert get_user_by_email(db_session, "new@tradingsolutions.com") is not None

        # Second attempt (different case) must NOT raise and must report no insert.
        again = create_user_if_absent(
            db_session,
            email="NEW@tradingsolutions.com",
            nombre_display="Dup",
            rol="inside_sales",
            created_by="admin@tradingsolutions.com",
        )
        assert again is False
        # DO NOTHING (not DO UPDATE): the original row is untouched.
        u = get_user_by_email(db_session, "new@tradingsolutions.com")
        assert u["nombre_display"] == "New"
        assert u["rol"] == "comercial"

    def test_insert_user_defaults_activo_true(self, db_session):
        from database.crud.users import insert_user, get_user_by_email
        insert_user(db_session, email="a@tradingsolutions.com", nombre_display="A", rol="otro")
        user = get_user_by_email(db_session, "a@tradingsolutions.com")
        assert user["activo"] is True


class TestUpdateUser:
    def test_update_rol(self, db_session):
        from database.crud.users import insert_user, update_user, get_user_by_email
        insert_user(db_session, email="u@tradingsolutions.com", nombre_display="U", rol="otro")
        update_user(db_session, "u@tradingsolutions.com", rol="comercial")
        assert get_user_by_email(db_session, "u@tradingsolutions.com")["rol"] == "comercial"

    def test_update_nombre_display(self, db_session):
        from database.crud.users import insert_user, update_user, get_user_by_email
        insert_user(db_session, email="u@tradingsolutions.com", nombre_display="Old", rol="otro")
        update_user(db_session, "u@tradingsolutions.com", nombre_display="New")
        assert get_user_by_email(db_session, "u@tradingsolutions.com")["nombre_display"] == "New"

    def test_update_multiple_fields(self, db_session):
        from database.crud.users import insert_user, update_user, get_user_by_email
        insert_user(db_session, email="u@tradingsolutions.com", nombre_display="Old", rol="otro")
        update_user(db_session, "u@tradingsolutions.com", nombre_display="New", rol="compliance")
        user = get_user_by_email(db_session, "u@tradingsolutions.com")
        assert user["nombre_display"] == "New"
        assert user["rol"] == "compliance"


class TestSetUserInactive:
    def test_set_inactive_keeps_row(self, db_session):
        from database.crud.users import insert_user, set_user_inactive, get_user_by_email
        insert_user(db_session, email="u@tradingsolutions.com", nombre_display="U", rol="comercial")
        set_user_inactive(db_session, "u@tradingsolutions.com")
        user = get_user_by_email(db_session, "u@tradingsolutions.com")
        assert user is not None
        assert user["activo"] is False

    def test_reactivate(self, db_session):
        from database.crud.users import insert_user, set_user_inactive, update_user, get_user_by_email
        insert_user(db_session, email="u@tradingsolutions.com", nombre_display="U", rol="comercial")
        set_user_inactive(db_session, "u@tradingsolutions.com")
        update_user(db_session, "u@tradingsolutions.com", activo=True)
        assert get_user_by_email(db_session, "u@tradingsolutions.com")["activo"] is True


class TestListUsers:
    def test_list_all_users(self, db_session):
        from database.crud.users import insert_user, list_users
        insert_user(db_session, email="a@tradingsolutions.com", nombre_display="A", rol="comercial")
        insert_user(db_session, email="b@tradingsolutions.com", nombre_display="B", rol="inside_sales")
        users = list_users(db_session, activo_only=False)
        emails = [u["email"] for u in users]
        assert "a@tradingsolutions.com" in emails
        assert "b@tradingsolutions.com" in emails

    def test_list_filtered_by_rol(self, db_session):
        from database.crud.users import insert_user, list_users
        insert_user(db_session, email="a@tradingsolutions.com", nombre_display="A", rol="comercial")
        insert_user(db_session, email="b@tradingsolutions.com", nombre_display="B", rol="inside_sales")
        comerciales = list_users(db_session, filter_rol="comercial")
        assert [u["email"] for u in comerciales] == ["a@tradingsolutions.com"]

    def test_list_active_only_default(self, db_session):
        from database.crud.users import insert_user, set_user_inactive, list_users
        insert_user(db_session, email="a@tradingsolutions.com", nombre_display="A", rol="comercial")
        insert_user(db_session, email="b@tradingsolutions.com", nombre_display="B", rol="comercial")
        set_user_inactive(db_session, "b@tradingsolutions.com")
        users = list_users(db_session)  # default activo_only=True
        assert [u["email"] for u in users] == ["a@tradingsolutions.com"]


class TestInsideSalesAssignments:
    def test_assign_comercial(self, db_session):
        from database.crud.users import insert_user
        from database.crud.inside_sales_assignments import assign_comercial, get_assignments_for_is
        insert_user(db_session, email="is@tradingsolutions.com", nombre_display="IS", rol="inside_sales")
        insert_user(db_session, email="c@tradingsolutions.com", nombre_display="C", rol="comercial")
        assign_comercial(db_session, "is@tradingsolutions.com", "c@tradingsolutions.com", assigned_by="admin@tradingsolutions.com")
        assignments = get_assignments_for_is(db_session, "is@tradingsolutions.com")
        assert [a["comercial_email"] for a in assignments] == ["c@tradingsolutions.com"]

    def test_assign_multiple_comerciales(self, db_session):
        from database.crud.users import insert_user
        from database.crud.inside_sales_assignments import assign_comercial, get_assignments_for_is
        insert_user(db_session, email="is@tradingsolutions.com", nombre_display="IS", rol="inside_sales")
        insert_user(db_session, email="c1@tradingsolutions.com", nombre_display="C1", rol="comercial")
        insert_user(db_session, email="c2@tradingsolutions.com", nombre_display="C2", rol="comercial")
        assign_comercial(db_session, "is@tradingsolutions.com", "c1@tradingsolutions.com")
        assign_comercial(db_session, "is@tradingsolutions.com", "c2@tradingsolutions.com")
        assignments = get_assignments_for_is(db_session, "is@tradingsolutions.com")
        assert len(assignments) == 2

    def test_remove_assignment(self, db_session):
        from database.crud.users import insert_user
        from database.crud.inside_sales_assignments import (
            assign_comercial, remove_assignment, get_assignments_for_is,
        )
        insert_user(db_session, email="is@tradingsolutions.com", nombre_display="IS", rol="inside_sales")
        insert_user(db_session, email="c1@tradingsolutions.com", nombre_display="C1", rol="comercial")
        insert_user(db_session, email="c2@tradingsolutions.com", nombre_display="C2", rol="comercial")
        assign_comercial(db_session, "is@tradingsolutions.com", "c1@tradingsolutions.com")
        assign_comercial(db_session, "is@tradingsolutions.com", "c2@tradingsolutions.com")
        remove_assignment(db_session, "is@tradingsolutions.com", "c1@tradingsolutions.com")
        assignments = get_assignments_for_is(db_session, "is@tradingsolutions.com")
        assert [a["comercial_email"] for a in assignments] == ["c2@tradingsolutions.com"]

    def test_get_inside_sales_for_comercial(self, db_session):
        """Inverse lookup: which IS are assigned to a comercial."""
        from database.crud.users import insert_user
        from database.crud.inside_sales_assignments import assign_comercial, get_inside_sales_for_comercial
        insert_user(db_session, email="is1@tradingsolutions.com", nombre_display="IS1", rol="inside_sales")
        insert_user(db_session, email="is2@tradingsolutions.com", nombre_display="IS2", rol="inside_sales")
        insert_user(db_session, email="c@tradingsolutions.com", nombre_display="C", rol="comercial")
        assign_comercial(db_session, "is1@tradingsolutions.com", "c@tradingsolutions.com")
        assign_comercial(db_session, "is2@tradingsolutions.com", "c@tradingsolutions.com")
        inside_sales = get_inside_sales_for_comercial(db_session, "c@tradingsolutions.com")
        emails = sorted([i["inside_sales_email"] for i in inside_sales])
        assert emails == ["is1@tradingsolutions.com", "is2@tradingsolutions.com"]

    def test_assignment_cascade_on_user_delete(self, db_session):
        """Deleting a user (IS or comercial) cascades to assignments."""
        from database.crud.users import insert_user
        from database.crud.inside_sales_assignments import assign_comercial, get_assignments_for_is
        insert_user(db_session, email="is@tradingsolutions.com", nombre_display="IS", rol="inside_sales")
        insert_user(db_session, email="c@tradingsolutions.com", nombre_display="C", rol="comercial")
        assign_comercial(db_session, "is@tradingsolutions.com", "c@tradingsolutions.com")
        # Delete comercial — assignment should cascade
        db_session.execute(text("DELETE FROM users WHERE email='c@tradingsolutions.com'"))
        db_session.commit()
        assert get_assignments_for_is(db_session, "is@tradingsolutions.com") == []
