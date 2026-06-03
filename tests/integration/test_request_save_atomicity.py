"""Atomicity of the request-save flow (forms/request_form.py::_save_request_to_db).

The parent ``requests`` row and its child registrations (customs/port/shipping)
must be persisted as a single transaction. If a child insert fails, NOTHING must
remain — otherwise compliance sees an orphaned request flagged has_port/has_customs
with no detail rows (the "borrado de datos al guardar" the comercial reported).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


def test_child_insert_failure_leaves_no_orphan_request(
    mock_streamlit, db_session, seed_profiles, monkeypatch
):
    import forms.request_form as rf

    def _boom(*args, **kwargs):
        raise SQLAlchemyError("simulated child insert failure")

    # Make the port-registration child insert fail mid-save.
    monkeypatch.setattr(rf, "insert_port_registration", _boom)

    result = rf._save_request_to_db(
        session=db_session,
        profile_id=seed_profiles["cliente"],
        company_name="Atomic Co",
        email=None,
        trading=None,
        location=None,
        language=None,
        reminder_frequency=None,
        tipo_solicitud="cliente",
        tipo_operacion=None,
        commodity=None,
        aduana=False,
        puerto=True,
        linea_naviera=False,
        requested_by="Tester",
        requested_by_type=None,
        tipo_aduana=[],
        terminales_seleccionados={"Cartagena": ["SPRC"]},
        tipo_linea=[],
        datos_msc={},
    )

    assert result is None, "save should report failure when a child insert fails"

    count = db_session.execute(
        text("SELECT COUNT(*) FROM requests WHERE company_name = :n"),
        {"n": "Atomic Co"},
    ).scalar()
    assert count == 0, "parent request must be rolled back when a child insert fails"
