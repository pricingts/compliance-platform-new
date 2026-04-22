"""Tests for services/mailer/templates.py — HTML email rendering.

Contract:
- Subject includes Case ID and company name.
- HTML body contains a banner with Case ID.
- All user-provided values are HTML-escaped (no XSS).
- Empty fields are omitted from the rendered table.
- All sheets_writer columns are supported.
- Footer mentions the compliance platform.
"""
from __future__ import annotations


def _full_payload():
    return {
        "Case ID": "C0042",
        "Fecha": "2026-04-18 10:00:00",
        "Solicitante": "Pedro Bruges",
        "Tipo de solicitud": "Cliente",
        "Nombre Compañía": "Acme Corp",
        "Correo": "contact@acme.com",
        "Cuenta Trading": "TS-CO",
        "País / Ubicación": "Colombia",
        "Idioma": "Español",
        "Frecuencia Recordatorio": "Semanal",
        "Tipo de Operación": "EXPO",
        "Commodity": "Coffee",
        "Aduana": "CARGOFLASH",
        "Puerto": "Cartagena",
        "Línea Naviera": "MSC",
    }


class TestRenderRequestEmail:
    def test_subject_contains_case_id_and_company(self):
        from services.mailer.templates import render_request_email

        payload = {"company_name": "Acme Corp"}
        subject, _ = render_request_email("C0042", payload)
        assert "C0042" in subject
        assert "Acme Corp" in subject

    def test_html_includes_case_id_banner(self):
        from services.mailer.templates import render_request_email

        payload = {"company_name": "Acme Corp"}
        _, html_body = render_request_email("C0042", payload)
        assert "case-banner" in html_body
        assert "C0042" in html_body

    def test_html_escapes_special_characters_in_values(self):
        from services.mailer.templates import render_request_email

        xss = "<script>alert('xss')</script>"
        payload = {"company_name": xss}
        _, html_body = render_request_email("C0042", payload)
        # Raw <script> must NOT appear; it should be escaped.
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body

    def test_empty_fields_are_omitted(self):
        from services.mailer.templates import render_request_email

        payload = {
            "company_name": "Acme Corp",
            "email": "",  # empty -> should be skipped
            "location": None,  # None -> should be skipped
            "commodity": "Coffee",
        }
        _, html_body = render_request_email("C0042", payload)
        # Commodity row should appear (the label should be present)
        assert "Commodity" in html_body
        # Correo row should be omitted — the label is there only for populated
        # rows; check we have no empty <td> pair after the "Correo" label.
        # Easiest: the full "Correo" label must not appear when value is empty.
        assert "<td>Correo</td>" not in html_body and "Correo</th>" not in html_body

    def test_renders_all_sheets_columns(self):
        from services.mailer.templates import render_request_email

        payload = {
            "requested_by": "Pedro Bruges",
            "tipo_solicitud": "Cliente",
            "company_name": "Acme Corp",
            "email": "c@acme.com",
            "trading": "TS-CO",
            "location": "Colombia",
            "language": "Español",
            "reminder_frequency": "Semanal",
            "tipo_operacion": "EXPO",
            "commodity": "Coffee",
            "aduana": "CARGOFLASH",
            "puerto": "Cartagena",
            "linea_naviera": "MSC",
        }
        _, html_body = render_request_email("C0042", payload)
        # Sample of the labels that must appear
        for label in (
            "Solicitante",
            "Tipo de solicitud",
            "Nombre Compañía",
            "Correo",
            "Cuenta Trading",
            "País / Ubicación",
            "Idioma",
            "Frecuencia Recordatorio",
            "Tipo de Operación",
            "Commodity",
            "Aduana",
            "Puerto",
            "Línea Naviera",
        ):
            assert label in html_body, f"Missing label in html: {label!r}"

    def test_footer_mentions_compliance_platform(self):
        from services.mailer.templates import render_request_email

        _, html_body = render_request_email("C0042", {"company_name": "X"})
        assert "Compliance Platform" in html_body


class TestInsideSalesBanner:
    """Phase 8.3: when an Inside Sales submits on behalf of a comercial
    (submitted_by_email != creator_email), the email must include a banner
    disclosing who submitted and on whose behalf."""

    def test_render_includes_is_banner_when_submitted_by_differs(self):
        from services.mailer.templates import render_request_email

        _, html_body = render_request_email(
            "C0042",
            {"company_name": "Acme Corp"},
            creator_email="is@tradingsolutions.com",
            submitted_by_email="comercial@tradingsolutions.com",
        )
        assert "sender-banner" in html_body
        assert "Enviado por:" in html_body
        assert "En nombre de:" in html_body
        assert "is@tradingsolutions.com" in html_body
        assert "comercial@tradingsolutions.com" in html_body

    def test_render_omits_is_banner_when_submitted_by_equals_creator(self):
        from services.mailer.templates import render_request_email

        _, html_body = render_request_email(
            "C0042",
            {"company_name": "Acme Corp"},
            creator_email="pedro@tradingsolutions.com",
            submitted_by_email="PEDRO@tradingsolutions.com",  # case-insensitive
        )
        assert "sender-banner" not in html_body
        assert "Enviado por:" not in html_body
        assert "En nombre de:" not in html_body

    def test_render_omits_is_banner_when_submitted_by_is_none(self):
        from services.mailer.templates import render_request_email

        _, html_body = render_request_email(
            "C0042",
            {"company_name": "Acme Corp"},
            creator_email="pedro@tradingsolutions.com",
            submitted_by_email=None,
        )
        assert "sender-banner" not in html_body
        assert "Enviado por:" not in html_body

    def test_render_omits_is_banner_when_creator_and_submitted_by_both_none(self):
        """Backward-compat: calling render_request_email without the new
        kwargs must behave exactly like before and not emit the banner."""
        from services.mailer.templates import render_request_email

        _, html_body = render_request_email(
            "C0042",
            {"company_name": "Acme Corp"},
        )
        assert "sender-banner" not in html_body
        assert "Enviado por:" not in html_body

    def test_render_escapes_creator_and_submitted_by_for_xss(self):
        """Addresses in the banner must be HTML-escaped — no raw <script>."""
        from services.mailer.templates import render_request_email

        _, html_body = render_request_email(
            "C0042",
            {"company_name": "Acme Corp"},
            creator_email="<script>alert('xss')</script>",
            submitted_by_email="<img src=x onerror=alert(1)>",
        )
        assert "<script>alert('xss')</script>" not in html_body
        assert "<img src=x onerror=alert(1)>" not in html_body
        # Escaped form must be present instead.
        assert "&lt;script&gt;" in html_body
        assert "&lt;img src=x onerror=alert(1)&gt;" in html_body
