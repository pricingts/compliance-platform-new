"""Tests for forms/request_form.py::_build_email_payload.

The helper is a pure function that assembles the dict consumed by the mailer
templates.  Its contract:

- Keys align with the snake_case keys declared in
  ``services/mailer/templates.py::_FIELD_MAP`` (requested_by, tipo_solicitud,
  company_name, email, trading, location, language, reminder_frequency,
  tipo_operacion, commodity, aduana, puerto, linea_naviera).
- Additional bookkeeping keys ``case_id`` and ``fecha`` are included so the
  email can mirror the Sheet row; the renderer will ignore them because they
  are not in ``_FIELD_MAP``.
- Empty / missing subfields in ``company_info`` / ``client_data`` collapse to
  empty strings (never ``None``).
- Multi-select fields (aduana, puerto, linea_naviera) render as the list
  contents joined by ``", "``, falling back to a plain ``"Sí"`` when the
  boolean flag is set but the list is empty.
"""
from __future__ import annotations


def test_build_email_payload_full_client(mock_streamlit):
    """A fully-populated cliente request includes every mailer key with
    the exact values from company_info / client_data."""
    from forms.request_form import _build_email_payload

    company_info = {
        "email": "contact@acme.com",
        "trading": "TS-CO",
        "location": "Colombia",
        "language": "Español",
        "reminder_frequency": "Semanal",
    }
    client_data = {
        "tipo_operacion": "EXPO",
        "commodity": "Coffee",
        "aduana": True,
        "tipo_aduana": ["CARGOFLASH", "SIGLO XXI"],
        "puerto": True,
        "terminales_seleccionados": {"Cartagena": ["SPRC"]},
        "linea_naviera": True,
        "tipo_linea": ["MSC", "MAERSK"],
    }

    payload = _build_email_payload(
        case_id="C0042",
        tipo_solicitud="cliente",
        company_name="Acme Corp",
        company_info=company_info,
        requested_by="Pedro Bruges",
        client_data=client_data,
    )

    assert payload["requested_by"] == "Pedro Bruges"
    assert payload["tipo_solicitud"] == "cliente"
    assert payload["company_name"] == "Acme Corp"
    assert payload["email"] == "contact@acme.com"
    assert payload["trading"] == "TS-CO"
    assert payload["location"] == "Colombia"
    assert payload["language"] == "Español"
    assert payload["reminder_frequency"] == "Semanal"
    assert payload["tipo_operacion"] == "EXPO"
    assert payload["commodity"] == "Coffee"
    assert payload["aduana"] == "CARGOFLASH, SIGLO XXI"
    assert payload["puerto"] == "Cartagena"
    assert payload["linea_naviera"] == "MSC, MAERSK"


def test_build_email_payload_provider_no_client_fields(mock_streamlit):
    """A proveedor has no tipo_operacion/commodity/aduana etc."""
    from forms.request_form import _build_email_payload

    company_info = {
        "email": "vendor@foo.com",
        "trading": "TS-PA",
        "location": "Panamá",
        "language": "Español",
        "reminder_frequency": "Mensual",
    }
    payload = _build_email_payload(
        case_id="C0100",
        tipo_solicitud="proveedor",
        company_name="Foo Suppliers",
        company_info=company_info,
        requested_by="Juan Supplier",
        client_data={},
    )

    assert payload["tipo_solicitud"] == "proveedor"
    assert payload["company_name"] == "Foo Suppliers"
    # Client-only keys should be empty strings (never absent or None).
    assert payload["tipo_operacion"] == ""
    assert payload["commodity"] == ""
    assert payload["aduana"] == ""
    assert payload["puerto"] == ""
    assert payload["linea_naviera"] == ""


def test_build_email_payload_handles_missing_fields_gracefully(mock_streamlit):
    """Missing company_info keys / None inputs must collapse to empty strings."""
    from forms.request_form import _build_email_payload

    payload = _build_email_payload(
        case_id=None,
        tipo_solicitud=None,
        company_name=None,
        company_info={},
        requested_by=None,
        client_data={},
    )
    assert payload["case_id"] == ""
    assert payload["tipo_solicitud"] == ""
    assert payload["company_name"] == ""
    assert payload["requested_by"] == ""
    assert payload["email"] == ""
    assert payload["trading"] == ""
    assert payload["location"] == ""
    assert payload["language"] == ""
    assert payload["reminder_frequency"] == ""


def test_build_email_payload_boolean_fallback_when_list_empty(mock_streamlit):
    """If aduana/puerto/linea_naviera are True but the list is empty, fall
    back to 'Sí' (consistent with the legacy sheets_writer rendering)."""
    from forms.request_form import _build_email_payload

    client_data = {
        "aduana": True,
        "tipo_aduana": [],
        "puerto": True,
        "terminales_seleccionados": {},
        "linea_naviera": True,
        "tipo_linea": [],
    }
    payload = _build_email_payload(
        case_id="C0001",
        tipo_solicitud="cliente",
        company_name="Edge Case Corp",
        company_info={"email": "e@e.com", "trading": "T", "location": "L",
                      "language": "X", "reminder_frequency": "Q"},
        requested_by="r",
        client_data=client_data,
    )
    assert payload["aduana"] == "Sí"
    assert payload["puerto"] == "Sí"
    assert payload["linea_naviera"] == "Sí"


def test_build_email_payload_keys_align_with_template_field_map(mock_streamlit):
    """Every snake_case key rendered by the mailer template must be produced
    by this helper — otherwise the email will miss fields silently."""
    from forms.request_form import _build_email_payload
    from services.mailer.templates import _FIELD_MAP

    payload = _build_email_payload(
        case_id="C0042",
        tipo_solicitud="cliente",
        company_name="Acme Corp",
        company_info={
            "email": "c@acme.com",
            "trading": "TS-CO",
            "location": "Colombia",
            "language": "Español",
            "reminder_frequency": "Semanal",
        },
        requested_by="Pedro",
        client_data={
            "tipo_operacion": "EXPO",
            "commodity": "Coffee",
            "aduana": True,
            "tipo_aduana": ["CARGOFLASH"],
            "puerto": True,
            "terminales_seleccionados": {"Cartagena": []},
            "linea_naviera": True,
            "tipo_linea": ["MSC"],
        },
    )
    for key, _label in _FIELD_MAP:
        assert key in payload, f"Template expects payload['{key}'] but builder did not set it"
