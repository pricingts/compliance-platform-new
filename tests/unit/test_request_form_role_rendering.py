"""Tests for the role-aware requester logic in forms/request_form.py.

Pure-function tests on `_build_requester_data`. The function decides, based
on the logged-in user's role, how to populate the requester fields in the
outgoing request payload.

Contract:
- rol='comercial'    → commercial = user's nombre_display, requested_by same,
                       type='comercial', submitted_by_email=None.
- rol='inside_sales' → commercial = the comercial dropdown value (mandatory),
                       requested_by = IS nombre_display, type='inside_sales',
                       submitted_by_email = IS email.
- rol='compliance' or 'otro' → commercial=None, requested_by=nombre_display,
                       type=rol, submitted_by_email=None.
- If an IS tries to submit without a selected comercial, the returned dict
  has `valid=False` and `error` explaining the issue.
"""
from __future__ import annotations


def _user(email="u@tradingsolutions.com", nombre="User", rol="otro", activo=True):
    return {"email": email, "nombre_display": nombre, "rol": rol, "activo": activo}


class TestBuildRequesterDataComercial:
    def test_comercial_gets_own_name(self):
        from forms.request_form import _build_requester_data
        user = _user(email="pedro@tradingsolutions.com", nombre="Pedro Bruges", rol="comercial")
        data = _build_requester_data(
            current_user=user,
            dropdown_value=None,   # ignored for comercial
            text_input_value=None,  # ignored for cliente+comercial
            assigned_comerciales=[],
        )
        assert data["requested_by"] == "Pedro Bruges"
        assert data["commercial"] == "Pedro Bruges"
        assert data["requested_by_type"] == "comercial"
        assert data["submitted_by_email"] is None
        assert data["valid"] is True


class TestBuildRequesterDataInsideSales:
    def test_inside_sales_with_selected_comercial(self):
        from forms.request_form import _build_requester_data
        user = _user(email="is@tradingsolutions.com", nombre="IS User", rol="inside_sales")
        data = _build_requester_data(
            current_user=user,
            dropdown_value="Andres Consuegra",
            text_input_value=None,
            assigned_comerciales=[
                {"email": "a@tradingsolutions.com", "nombre_display": "Andres Consuegra"},
                {"email": "p@tradingsolutions.com", "nombre_display": "Pedro Bruges"},
            ],
        )
        assert data["commercial"] == "Andres Consuegra"
        assert data["requested_by"] == "IS User"
        assert data["requested_by_type"] == "inside_sales"
        assert data["submitted_by_email"] == "is@tradingsolutions.com"
        assert data["valid"] is True

    def test_inside_sales_no_comerciales_assigned_is_invalid(self):
        from forms.request_form import _build_requester_data
        user = _user(email="is@tradingsolutions.com", nombre="IS User", rol="inside_sales")
        data = _build_requester_data(
            current_user=user,
            dropdown_value=None,
            text_input_value=None,
            assigned_comerciales=[],
        )
        assert data["valid"] is False
        assert "comercial" in data["error"].lower()

    def test_inside_sales_no_selection_is_invalid(self):
        from forms.request_form import _build_requester_data
        user = _user(email="is@tradingsolutions.com", nombre="IS User", rol="inside_sales")
        data = _build_requester_data(
            current_user=user,
            dropdown_value=None,
            text_input_value=None,
            assigned_comerciales=[
                {"email": "a@tradingsolutions.com", "nombre_display": "Andres Consuegra"}
            ],
        )
        assert data["valid"] is False


class TestBuildRequesterDataOtro:
    def test_otro_role_no_commercial_field(self):
        from forms.request_form import _build_requester_data
        user = _user(email="x@tradingsolutions.com", nombre="X User", rol="otro")
        data = _build_requester_data(
            current_user=user,
            dropdown_value=None,
            text_input_value=None,
            assigned_comerciales=[],
        )
        assert data["commercial"] is None
        assert data["requested_by"] == "X User"
        assert data["requested_by_type"] == "otro"
        assert data["submitted_by_email"] is None
        assert data["valid"] is True


class TestBuildRequesterDataCompliance:
    def test_compliance_no_commercial_field(self):
        from forms.request_form import _build_requester_data
        user = _user(email="jsanchez@tradingsolutions.com", nombre="Juan Sanchez", rol="compliance")
        data = _build_requester_data(
            current_user=user,
            dropdown_value=None,
            text_input_value=None,
            assigned_comerciales=[],
        )
        assert data["commercial"] is None
        assert data["requested_by"] == "Juan Sanchez"
        assert data["requested_by_type"] == "compliance"
        assert data["submitted_by_email"] is None
        assert data["valid"] is True


class TestBuildRequesterDataProveedor:
    """For providers, any role uses the text_input flow (legacy behavior)."""

    def test_provider_uses_text_input(self):
        from forms.request_form import _build_requester_data
        user = _user(email="x@tradingsolutions.com", nombre="X", rol="otro")
        data = _build_requester_data(
            current_user=user,
            dropdown_value=None,
            text_input_value="Alguien externo",
            assigned_comerciales=[],
            tipo_solicitud="proveedor",
        )
        assert data["requested_by"] == "Alguien externo"
        assert data["requested_by_type"] == "solicitante_proveedor"
        assert data["commercial"] is None
        assert data["valid"] is True

    def test_provider_missing_name_invalid(self):
        from forms.request_form import _build_requester_data
        user = _user(email="x@tradingsolutions.com", nombre="X", rol="otro")
        data = _build_requester_data(
            current_user=user,
            dropdown_value=None,
            text_input_value=None,
            assigned_comerciales=[],
            tipo_solicitud="proveedor",
        )
        assert data["valid"] is False


class TestInsertWithSubmittedByEmail:
    def test_persists_submitted_by_email(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request
        from sqlalchemy import text
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="is@tradingsolutions.com",
            submitted_by_email="is@tradingsolutions.com",
        )
        row = db_session.execute(
            text("SELECT submitted_by_email FROM requests WHERE id=:id"),
            {"id": rid},
        ).fetchone()
        assert row[0] == "is@tradingsolutions.com"

    def test_defaults_to_none(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request
        from sqlalchemy import text
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="c@tradingsolutions.com",
        )
        row = db_session.execute(
            text("SELECT submitted_by_email FROM requests WHERE id=:id"),
            {"id": rid},
        ).fetchone()
        assert row[0] is None
