"""Integration tests for the request-creation flow with mailer hook (Phase 3).

Rendering ``forms()`` in a test harness is not practical — the function is
built around Streamlit widgets, the native submission cycle, and session-state
rehydration. Instead, this module exercises the *service chain* that the form
delegates to: ``insert_client_request`` + ``save_request`` +
``send_request_notification``. The payload helper is covered in
``tests/unit/test_build_email_payload.py``.

All tests run offline:
  * ``mock_smtp`` from conftest replaces ``smtplib.SMTP_SSL`` and seeds
    ``st.secrets['smtp']`` / ``st.secrets['mailer']`` with sane defaults.
  * Google Sheets is patched via ``services.sheets_writer.save_request``.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.integration


def _run_request_chain(
    db_session,
    seed_profiles,
    *,
    company_name: str = "Acme Corp",
    creator_email: str = "pedro@tradingsolutions.com",
    submitted_by_email: str | None = None,
    mailer_should_raise: Exception | None = None,
):
    """Drive the full service chain the form would trigger on submit.

    Mirrors the sequence ``forms/request_form.forms()`` runs after the user
    clicks "Guardar", minus the Drive attachments branch. Returns the resolved
    ``(request_id, case_id, warnings_log)``. ``warnings_log`` is a list of
    ``(level, message)`` tuples captured from the `st.warning` mock so tests
    can assert on the UI feedback triggered by the mailer branch.
    """
    # 1. Create the request row (drives case_id)
    from database.crud.clientes import insert_client_request, get_case_id

    request_id = insert_client_request(
        db_session,
        profile_id=seed_profiles["cliente"],
        company_name=company_name,
        email="contact@acme.com",
        trading="TS-CO",
        location="Colombia",
        language="Español",
        reminder_frequency="Semanal",
        operation_type="EXPO",
        commodity="Coffee",
        has_customs=True,
        has_port=False,
        has_shipping_line=False,
        requested_by="Pedro Bruges",
        requested_by_type="comercial",
        user_email=creator_email,
        submitted_by_email=submitted_by_email,
    )
    case_id = get_case_id(db_session, request_id)

    # 2. Build the mailer payload (same helper the form uses)
    from forms.request_form import _build_email_payload
    payload = _build_email_payload(
        case_id=case_id,
        tipo_solicitud="cliente",
        company_name=company_name,
        company_info={
            "email": "contact@acme.com",
            "trading": "TS-CO",
            "location": "Colombia",
            "language": "Español",
            "reminder_frequency": "Semanal",
        },
        requested_by="Pedro Bruges",
        client_data={
            "tipo_operacion": "EXPO",
            "commodity": "Coffee",
            "aduana": True,
            "tipo_aduana": ["CARGOFLASH"],
            "puerto": False,
            "terminales_seleccionados": {},
            "linea_naviera": False,
            "tipo_linea": [],
        },
    )

    # 3. Invoke the mailer. Patch send_request_notification where the form
    #    imports it from (services.mailer) so we control its side effects.
    from services import mailer as mailer_pkg

    mock_send = MagicMock()
    if mailer_should_raise is not None:
        mock_send.side_effect = mailer_should_raise
    else:
        mock_send.return_value = True

    warnings_log: list[tuple[str, str]] = []

    def _fake_warning(msg, *a, **kw):
        warnings_log.append(("warning", str(msg)))

    with patch.object(mailer_pkg, "send_request_notification", mock_send), \
         patch("streamlit.warning", side_effect=_fake_warning):
        # This mirrors the try/except block we will add to forms/request_form.py.
        from utils.exceptions import MailerError
        from utils.error_handlers import sanitize_for_user

        try:
            mailer_pkg.send_request_notification(
                session=db_session,
                case_id=case_id,
                payload=payload,
                creator_email=creator_email,
                submitted_by_email=submitted_by_email,
            )
        except MailerError as e:
            import streamlit as st
            st.warning(sanitize_for_user(e))
        except Exception:
            import streamlit as st
            st.warning(
                "Solicitud guardada. Hubo un problema notificando a compliance por correo."
            )

    return request_id, case_id, warnings_log, mock_send


class TestCreateRequestFlow:
    """Happy path + failure modes of the service chain triggered by the form."""

    def test_invokes_mailer_after_request_persisted(
        self, db_session, seed_profiles, mock_smtp
    ):
        """Service chain reaches send_request_notification with case_id and
        creator_email extracted from the row we just inserted."""
        request_id, case_id, _warnings, mock_send = _run_request_chain(
            db_session, seed_profiles
        )

        assert case_id is not None and case_id.startswith("C")
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["case_id"] == case_id
        assert kwargs["creator_email"] == "pedro@tradingsolutions.com"
        assert kwargs["session"] is db_session

        # Request row is in the DB regardless of mailer outcome
        row = db_session.execute(
            text("SELECT id, case_id FROM requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()
        assert row is not None
        assert row[1] == case_id

    def test_survives_mailer_error_without_losing_request(
        self, db_session, seed_profiles, mock_smtp
    ):
        """A MailerError from the service must not propagate to the caller.

        The request row must remain committed, and the user is warned via
        ``st.warning`` (we cannot assert on the warning here because the real
        form swallows it — but the call-chain above does it)."""
        from utils.exceptions import MailerError

        request_id, case_id, warnings_log, _mock_send = _run_request_chain(
            db_session,
            seed_profiles,
            mailer_should_raise=MailerError("SMTP auth failed"),
        )

        # Request is persisted
        row = db_session.execute(
            text("SELECT id FROM requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()
        assert row is not None

        # A user-visible warning was emitted
        assert len(warnings_log) == 1
        level, message = warnings_log[0]
        assert level == "warning"
        # sanitize_for_user returns the canonical MailerError message
        assert "correo" in message.lower()

    def test_skips_mailer_when_flag_off(
        self, db_session, seed_profiles, mock_smtp
    ):
        """With mailer.enabled = False the real send_request_notification
        returns False. No warning should be emitted."""
        # Disable the flag before running. Use the *real* mailer to exercise
        # the guard in services/mailer/__init__.py::_is_feature_enabled.
        mock_smtp["secrets"]["mailer"] = {"enabled": False}

        from database.crud.clientes import insert_client_request, get_case_id
        from services.mailer import send_request_notification

        request_id = insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Flag Off Corp",
            email="foo@bar.com",
            trading="TS-CO",
            location="Colombia",
            language="Español",
            reminder_frequency="Semanal",
            requested_by="Pedro",
            requested_by_type="comercial",
            user_email="pedro@tradingsolutions.com",
        )
        case_id = get_case_id(db_session, request_id)

        warnings_log: list[tuple[str, str]] = []
        with patch(
            "streamlit.warning",
            side_effect=lambda m, *a, **kw: warnings_log.append(("warning", str(m))),
        ):
            result = send_request_notification(
                session=db_session,
                case_id=case_id,
                payload={"company_name": "Flag Off Corp"},
                creator_email="pedro@tradingsolutions.com",
            )

        assert result is False
        # The flag-off branch is NOT an error -> no warning should fire
        assert warnings_log == []
        # SMTP was not hit
        assert not mock_smtp["instance_ssl"].send_message.called

    def test_sanitized_message_on_error_has_no_stack_trace(
        self, db_session, seed_profiles, mock_smtp
    ):
        """The warning message shown to the user must come from
        ``sanitize_for_user`` — no class name, no traceback, no raw exception
        string."""
        from utils.exceptions import MailerError

        _rid, _cid, warnings_log, _mock_send = _run_request_chain(
            db_session,
            seed_profiles,
            mailer_should_raise=MailerError(
                "Traceback (most recent call last):\n"
                '  File "x.py", line 1, in y\n'
                "    raise Exception('boom')"
            ),
        )

        assert len(warnings_log) == 1
        message = warnings_log[0][1]
        # No raw stack trace artifacts
        assert "Traceback" not in message
        assert "line" not in message.lower() or "inicia" in message.lower()
        assert "File " not in message
        assert "raise" not in message
        # The user-facing message is the canonical MailerError response
        assert "correo" in message.lower()
