"""Tests for the 'Mis Solicitudes' personal dashboard (Phase 6 / F6).

Covers:
- get_my_requests filters by owner OR submitter (Inside Sales scenario).
- aggregate_status reduces a list of registration statuses to one global status.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture
def seeded_requests(db_session, seed_profiles, seed_statuses):
    """Three requests:
    - r1 owner=alice, no submitter
    - r2 owner=alice, submitter=bob (alice is the IS, bob the comercial — actually
        for Phase 6 we need: user_email = the one who created (alice IS),
        submitted_by_email = alice (IS herself in our model).
        Let's keep it simple: r1 owner=alice, r2 owner=alice + submitter=alice,
        r3 owner=eve.
    - r3 owner=eve, no submitter
    """
    pid = seed_profiles["cliente"]
    db_session.execute(text("""
        INSERT INTO requests (profile_id, company_name, user_email, case_id)
        VALUES (:pid, 'Acme', 'alice@tradingsolutions.com', 'C0001')
    """), {"pid": pid})
    db_session.execute(text("""
        INSERT INTO requests (profile_id, company_name, user_email, submitted_by_email, case_id)
        VALUES (:pid, 'Beta', 'alice@tradingsolutions.com', 'alice@tradingsolutions.com', 'C0002')
    """), {"pid": pid})
    db_session.execute(text("""
        INSERT INTO requests (profile_id, company_name, user_email, case_id)
        VALUES (:pid, 'Gamma', 'eve@tradingsolutions.com', 'C0003')
    """), {"pid": pid})
    db_session.commit()


class TestGetMyRequests:
    def test_returns_owner_requests(self, db_session, seeded_requests):
        from database.crud.my_requests import get_my_requests
        rows = get_my_requests(db_session, "alice@tradingsolutions.com")
        case_ids = sorted([r["case_id"] for r in rows])
        assert "C0001" in case_ids and "C0002" in case_ids
        assert "C0003" not in case_ids

    def test_returns_submitter_requests(self, db_session, seed_profiles):
        """An IS who submits for a comercial (different user_email) sees those rows."""
        from database.crud.my_requests import get_my_requests
        pid = seed_profiles["cliente"]
        db_session.execute(text("""
            INSERT INTO requests (profile_id, company_name, user_email, submitted_by_email, case_id)
            VALUES (:pid, 'IS-created', 'comercial@tradingsolutions.com', 'is@tradingsolutions.com', 'C9001')
        """), {"pid": pid})
        db_session.commit()
        rows = get_my_requests(db_session, "is@tradingsolutions.com")
        case_ids = [r["case_id"] for r in rows]
        assert "C9001" in case_ids

    def test_excludes_others(self, db_session, seeded_requests):
        from database.crud.my_requests import get_my_requests
        rows = get_my_requests(db_session, "stranger@tradingsolutions.com")
        assert rows == []

    def test_orders_newest_first(self, db_session, seed_profiles):
        """Most-recent created_at first."""
        from database.crud.my_requests import get_my_requests
        pid = seed_profiles["cliente"]
        db_session.execute(text("""
            INSERT INTO requests (profile_id, company_name, user_email, case_id, created_at)
            VALUES (:pid, 'Old', 'me@tradingsolutions.com', 'C9001', '2026-01-01 00:00:00')
        """), {"pid": pid})
        db_session.execute(text("""
            INSERT INTO requests (profile_id, company_name, user_email, case_id, created_at)
            VALUES (:pid, 'New', 'me@tradingsolutions.com', 'C9002', '2026-04-14 00:00:00')
        """), {"pid": pid})
        db_session.commit()
        rows = get_my_requests(db_session, "me@tradingsolutions.com")
        assert rows[0]["case_id"] == "C9002"
        assert rows[1]["case_id"] == "C9001"

    def test_case_insensitive(self, db_session, seeded_requests):
        from database.crud.my_requests import get_my_requests
        rows = get_my_requests(db_session, "ALICE@tradingsolutions.com")
        case_ids = sorted([r["case_id"] for r in rows])
        assert "C0001" in case_ids and "C0002" in case_ids


class TestRenderMyRequestsPassesSession:
    """Regression tests for the latent bug fixed in this commit: the view was
    calling ``get_last_status_change_time("request", r["id"])`` without the
    ``session`` argument, triggering a silent ``TypeError`` that was swallowed
    by the narrowed except in forms/my_requests_view.py.
    """

    def test_get_last_status_change_time_is_called_with_session(
        self, db_session, seed_profiles, seed_statuses, mock_streamlit, monkeypatch
    ):
        """Assert the CRUD helper is invoked with (session, entity_type, entity_id)."""
        from datetime import datetime
        from unittest.mock import MagicMock

        # Seed one request owned by alice.
        pid = seed_profiles["cliente"]
        db_session.execute(text("""
            INSERT INTO requests (profile_id, company_name, user_email, case_id)
            VALUES (:pid, 'Acme', 'alice@tradingsolutions.com', 'C0001')
        """), {"pid": pid})
        db_session.commit()

        # Patch CRUD helper where the view imports it.
        fake_last_change = datetime(2026, 4, 10, 12, 0, 0)
        mock_helper = MagicMock(return_value=fake_last_change)
        monkeypatch.setattr(
            "forms.my_requests_view.get_last_status_change_time", mock_helper
        )

        # Patch st components the view renders so we can import render_my_requests.
        monkeypatch.setattr("streamlit.dataframe", MagicMock())
        monkeypatch.setattr("streamlit.columns", MagicMock(return_value=[
            MagicMock(), MagicMock(), MagicMock(), MagicMock()
        ]))
        monkeypatch.setattr("streamlit.caption", MagicMock())
        monkeypatch.setattr("streamlit.info", MagicMock())
        monkeypatch.setattr("streamlit.markdown", MagicMock())
        monkeypatch.setattr("streamlit.metric", MagicMock())
        # Neutralize a SQLite-only quirk: rows return created_at as str, not datetime.
        monkeypatch.setattr("forms.my_requests_view.to_colombia_tz", lambda x: x)

        from forms.my_requests_view import render_my_requests
        render_my_requests(db_session, "alice@tradingsolutions.com")

        # Must have been called at least once, and with session as first arg.
        assert mock_helper.call_count >= 1
        first_call_args = mock_helper.call_args_list[0]
        # Accept either positional or keyword passing of session.
        args, kwargs = first_call_args
        if args:
            assert args[0] is db_session, (
                "First positional argument must be the SQLAlchemy session"
            )
            assert args[1] == "request"
        else:
            assert kwargs.get("session") is db_session
            assert kwargs.get("entity_type") == "request"

    def test_get_last_status_change_time_receives_entity_id(
        self, db_session, seed_profiles, seed_statuses, mock_streamlit, monkeypatch
    ):
        """Assert the CRUD helper also receives the correct request id as entity_id."""
        from unittest.mock import MagicMock

        pid = seed_profiles["cliente"]
        db_session.execute(text("""
            INSERT INTO requests (profile_id, company_name, user_email, case_id)
            VALUES (:pid, 'Acme', 'alice@tradingsolutions.com', 'C0200')
        """), {"pid": pid})
        db_session.commit()
        request_id = db_session.execute(
            text("SELECT id FROM requests WHERE case_id = 'C0200'")
        ).scalar()

        # Return None so days_label handles it gracefully (returns '—').
        mock_helper = MagicMock(return_value=None)
        monkeypatch.setattr(
            "forms.my_requests_view.get_last_status_change_time", mock_helper
        )
        monkeypatch.setattr("streamlit.dataframe", MagicMock())
        monkeypatch.setattr("streamlit.columns", MagicMock(return_value=[
            MagicMock(), MagicMock(), MagicMock(), MagicMock()
        ]))
        monkeypatch.setattr("streamlit.caption", MagicMock())
        monkeypatch.setattr("streamlit.info", MagicMock())
        monkeypatch.setattr("streamlit.markdown", MagicMock())
        monkeypatch.setattr("streamlit.metric", MagicMock())
        monkeypatch.setattr("forms.my_requests_view.to_colombia_tz", lambda x: x)

        from forms.my_requests_view import render_my_requests
        render_my_requests(db_session, "alice@tradingsolutions.com")

        # entity_type == 'request' and entity_id == the request we just seeded.
        call_args = mock_helper.call_args_list[0]
        args, kwargs = call_args
        if args:
            assert args[1] == "request"
            assert args[2] == request_id
        else:
            assert kwargs.get("entity_type") == "request"
            assert kwargs.get("entity_id") == request_id


class TestAggregateStatus:
    def test_all_approved_is_completa(self):
        from database.crud.my_requests import aggregate_status
        assert aggregate_status(["aprobado", "aprobado", "aprobado"]) == "Completa"

    def test_any_rejected_is_con_rechazos(self):
        from database.crud.my_requests import aggregate_status
        assert aggregate_status(["aprobado", "rechazado", "aprobado"]) == "Con rechazos"
        # Even if everything else is "en revision"
        assert aggregate_status(["en revision", "rechazado"]) == "Con rechazos"

    def test_any_in_review_is_en_revision(self):
        from database.crud.my_requests import aggregate_status
        assert aggregate_status(["aprobado", "en revision"]) == "En revisión"

    def test_no_registrations_is_pendiente(self):
        from database.crud.my_requests import aggregate_status
        assert aggregate_status([]) == "Pendiente"

    def test_only_pending_is_pendiente(self):
        from database.crud.my_requests import aggregate_status
        assert aggregate_status(["pendiente", "pendiente"]) == "Pendiente"
