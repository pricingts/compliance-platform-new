"""Tests for Phase 8.2 — mailer transport router + threading headers.

Contract under test:
- ``_resolve_transport()`` reads ``st.secrets['mailer']['transport']`` and
  returns ``'smtp'`` (default / missing) or ``'gmail'`` (when configured).
  Unknown values fall back to ``'smtp'`` and log a warning.
- ``_build_threading_headers(session, request_id)`` returns
  ``(None, None, None)`` for the first email of a request, and
  ``(references, in_reply_to, thread_id)`` when a prior ``email_threads``
  row exists.
- ``send_request_notification`` dispatches to the configured transport:
    * SMTP by default (backward-compat with tests that predate Phase 8.2).
    * Gmail API when ``transport='gmail'``, persisting the returned
      ``threadId`` into ``email_threads``.
- On success, ``email_threads`` is upserted regardless of transport so the
  ``last_message_id`` accumulates into the References chain and a future
  migration to Gmail can thread existing cases correctly.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy import text


# ---------------------------------------------------------------------------
# Seed helpers (mirror the pattern from test_mailer_send_request_notification)
# ---------------------------------------------------------------------------

def _seed_request(db_session, seed_profiles, case_id="C0999"):
    db_session.execute(
        text(
            """
            INSERT INTO requests (profile_id, company_name, user_email, case_id)
            VALUES (:pid, 'Router Test', 'creator@tradingsolutions.com', :case_id)
            """
        ),
        {"pid": seed_profiles["cliente"], "case_id": case_id},
    )
    db_session.commit()
    return db_session.execute(
        text("SELECT id FROM requests WHERE case_id = :c"), {"c": case_id}
    ).scalar()


def _seed_thread(
    db_session,
    request_id,
    gmail_thread_id="T1",
    last_message_id="<m1@compliance.tradingsolutions.com>",
    references_chain="",
):
    db_session.execute(
        text(
            """
            INSERT INTO email_threads
                (request_id, gmail_thread_id, last_message_id, references_chain)
            VALUES (:rid, :tid, :mid, :ref)
            """
        ),
        {
            "rid": request_id,
            "tid": gmail_thread_id,
            "mid": last_message_id,
            "ref": references_chain,
        },
    )
    db_session.commit()


# ---------------------------------------------------------------------------
# _build_threading_headers
# ---------------------------------------------------------------------------

class TestBuildThreadingHeaders:
    def test_returns_none_when_no_thread(self, db_session, seed_profiles):
        from services.mailer import _build_threading_headers

        rid = _seed_request(db_session, seed_profiles)
        assert _build_threading_headers(db_session, rid) == (None, None, None)

    def test_returns_chain_when_thread_exists(self, db_session, seed_profiles):
        from services.mailer import _build_threading_headers

        rid = _seed_request(db_session, seed_profiles)
        _seed_thread(
            db_session,
            rid,
            gmail_thread_id="T1",
            last_message_id="<m1@compliance.tradingsolutions.com>",
            references_chain="",
        )
        refs, irt, tid = _build_threading_headers(db_session, rid)
        assert refs == "<m1@compliance.tradingsolutions.com>"
        assert irt == "<m1@compliance.tradingsolutions.com>"
        assert tid == "T1"

    def test_chain_accumulates(self, db_session, seed_profiles):
        from services.mailer import _build_threading_headers

        rid = _seed_request(db_session, seed_profiles)
        _seed_thread(
            db_session,
            rid,
            gmail_thread_id="T2",
            last_message_id="<m1@compliance.tradingsolutions.com>",
            references_chain="<m0@compliance.tradingsolutions.com>",
        )
        refs, irt, tid = _build_threading_headers(db_session, rid)
        assert refs == (
            "<m0@compliance.tradingsolutions.com> "
            "<m1@compliance.tradingsolutions.com>"
        )
        assert irt == "<m1@compliance.tradingsolutions.com>"
        assert tid == "T2"


# ---------------------------------------------------------------------------
# _resolve_transport
# ---------------------------------------------------------------------------

class TestResolveTransport:
    def test_default_transport_is_smtp(self):
        """Without any Streamlit secrets configured, default is SMTP."""
        from services.mailer import _resolve_transport

        # No mock_streamlit fixture here: st.secrets likely raises, which the
        # helper swallows and treats as "no config -> smtp".
        assert _resolve_transport() == "smtp"

    def test_missing_transport_key_is_smtp(self, mock_streamlit):
        from services.mailer import _resolve_transport

        mock_streamlit["secrets"]["mailer"] = {"enabled": True}
        assert _resolve_transport() == "smtp"

    def test_explicit_smtp_is_smtp(self, mock_streamlit):
        from services.mailer import _resolve_transport

        mock_streamlit["secrets"]["mailer"] = {
            "enabled": True,
            "transport": "smtp",
        }
        assert _resolve_transport() == "smtp"

    def test_explicit_gmail_is_gmail(self, mock_streamlit):
        from services.mailer import _resolve_transport

        mock_streamlit["secrets"]["mailer"] = {
            "enabled": True,
            "transport": "gmail",
        }
        assert _resolve_transport() == "gmail"

    def test_unknown_transport_falls_back_to_smtp_with_warning(
        self, mock_streamlit, monkeypatch
    ):
        import services.mailer as mailer_pkg

        mock_streamlit["secrets"]["mailer"] = {
            "enabled": True,
            "transport": "carrier_pigeon",
        }
        captured: list[tuple[str, tuple]] = []

        def fake_warning(msg, *args, **kwargs):
            captured.append((msg, args))

        monkeypatch.setattr(mailer_pkg.logger, "warning", fake_warning)
        assert mailer_pkg._resolve_transport() == "smtp"
        assert captured, "expected a logger.warning call on unknown transport"
        assert any("carrier_pigeon" in repr(c) for c in captured)


# ---------------------------------------------------------------------------
# Router dispatch via send_request_notification
# ---------------------------------------------------------------------------

class TestRouterDispatch:
    def test_routes_to_smtp_by_default(
        self, db_session, seed_profiles, mock_smtp, monkeypatch
    ):
        """Without a `transport` flag, we must still call SMTP — not Gmail."""
        from services.mailer import send_request_notification

        _seed_request(db_session, seed_profiles, case_id="C0801")

        # Safety net: if we accidentally import gmail_client, blow up.
        import services.mailer.gmail_client as gmail_client
        gmail_send = MagicMock(
            side_effect=AssertionError("gmail_client.send_email must NOT be called"),
        )
        monkeypatch.setattr(gmail_client, "send_email", gmail_send)

        result = send_request_notification(
            session=db_session,
            case_id="C0801",
            payload={"company_name": "Router Test"},
            creator_email="creator@tradingsolutions.com",
        )
        assert result is True
        assert mock_smtp["instance_ssl"].send_message.called
        assert not gmail_send.called

    def test_routes_to_gmail_when_configured(
        self, db_session, seed_profiles, mock_smtp, monkeypatch
    ):
        """With ``transport='gmail'`` only Gmail API is called."""
        from services.mailer import send_request_notification
        import services.mailer.gmail_client as gmail_client

        mock_smtp["secrets"]["mailer"] = {
            "enabled": True,
            "transport": "gmail",
        }

        _seed_request(db_session, seed_profiles, case_id="C0802")

        gmail_send = MagicMock(
            return_value={
                "id": "gmail-msg-1",
                "threadId": "gmail-thread-1",
                "labelIds": ["SENT"],
            }
        )
        monkeypatch.setattr(gmail_client, "send_email", gmail_send)

        result = send_request_notification(
            session=db_session,
            case_id="C0802",
            payload={"company_name": "Router Test"},
            creator_email="creator@tradingsolutions.com",
        )
        assert result is True
        assert gmail_send.called
        _, kwargs = gmail_send.call_args
        assert kwargs["creator_email"] == "creator@tradingsolutions.com"
        # First send for this case: no threading hints.
        assert kwargs["thread_id"] is None
        assert kwargs["references"] is None
        assert kwargs["in_reply_to"] is None
        assert kwargs["message_id"].startswith("<case-C0802-creation@")
        # And SMTP must NOT have been touched.
        assert not mock_smtp["instance_ssl"].send_message.called

    def test_gmail_response_persists_thread_to_db(
        self, db_session, seed_profiles, mock_smtp, monkeypatch
    ):
        """Successful Gmail send must upsert email_threads with the threadId."""
        from services.mailer import send_request_notification
        import services.mailer.gmail_client as gmail_client

        mock_smtp["secrets"]["mailer"] = {
            "enabled": True,
            "transport": "gmail",
        }

        rid = _seed_request(db_session, seed_profiles, case_id="C0803")

        gmail_send = MagicMock(
            return_value={
                "id": "gmail-msg-abc",
                "threadId": "gmail-thread-T1",
                "labelIds": ["SENT"],
            }
        )
        monkeypatch.setattr(gmail_client, "send_email", gmail_send)

        send_request_notification(
            session=db_session,
            case_id="C0803",
            payload={"company_name": "Router Test"},
            creator_email="creator@tradingsolutions.com",
        )

        row = db_session.execute(
            text(
                "SELECT request_id, gmail_thread_id, last_message_id "
                "FROM email_threads WHERE request_id = :rid"
            ),
            {"rid": rid},
        ).fetchone()
        assert row is not None
        assert row[0] == rid
        assert row[1] == "gmail-thread-T1"
        assert row[2] == "<case-C0803-creation@compliance.tradingsolutions.com>"

    def test_smtp_send_also_persists_thread_with_null_gmail_id(
        self, db_session, seed_profiles, mock_smtp
    ):
        """SMTP path still persists last_message_id so a later Gmail migration
        can reconstruct the References chain. gmail_thread_id stays NULL."""
        from services.mailer import send_request_notification

        rid = _seed_request(db_session, seed_profiles, case_id="C0804")

        send_request_notification(
            session=db_session,
            case_id="C0804",
            payload={"company_name": "Router Test"},
            creator_email="creator@tradingsolutions.com",
        )

        row = db_session.execute(
            text(
                "SELECT gmail_thread_id, last_message_id "
                "FROM email_threads WHERE request_id = :rid"
            ),
            {"rid": rid},
        ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] == "<case-C0804-creation@compliance.tradingsolutions.com>"

    def test_gmail_transport_excludes_creator_from_cc(
        self, db_session, seed_profiles, mock_smtp, monkeypatch
    ):
        """Phase 8.3: when transport=gmail, creator is From, so it must
        NOT appear in CC. submitted_by_email stays in CC."""
        from services.mailer import send_request_notification
        import services.mailer.gmail_client as gmail_client

        mock_smtp["secrets"]["mailer"] = {
            "enabled": True,
            "transport": "gmail",
        }

        _seed_request(db_session, seed_profiles, case_id="C0805")

        gmail_send = MagicMock(
            return_value={
                "id": "gmail-msg-x",
                "threadId": "gmail-thread-x",
                "labelIds": ["SENT"],
            }
        )
        monkeypatch.setattr(gmail_client, "send_email", gmail_send)

        send_request_notification(
            session=db_session,
            case_id="C0805",
            payload={"company_name": "Router Test"},
            creator_email="creator@tradingsolutions.com",
            submitted_by_email="comercial@tradingsolutions.com",
        )

        assert gmail_send.called
        _, kwargs = gmail_send.call_args
        cc = kwargs["cc"] or []
        cc_lower = [e.lower() for e in cc]
        # Creator is the From — must NOT be in CC.
        assert "creator@tradingsolutions.com" not in cc_lower
        # Submitted-by must still be in CC.
        assert "comercial@tradingsolutions.com" in cc_lower

    def test_smtp_transport_keeps_creator_in_cc(
        self, db_session, seed_profiles, mock_smtp
    ):
        """Pre-Phase-8.3 behavior on SMTP: creator stays in CC
        (because SMTP uses a shared From header, not the creator)."""
        from services.mailer import send_request_notification

        _seed_request(db_session, seed_profiles, case_id="C0806")

        send_request_notification(
            session=db_session,
            case_id="C0806",
            payload={"company_name": "Router Test"},
            creator_email="creator@tradingsolutions.com",
            submitted_by_email="comercial@tradingsolutions.com",
        )

        sent_msg = mock_smtp["instance_ssl"].send_message.call_args[0][0]
        cc_header = sent_msg["Cc"] or ""
        assert "creator@tradingsolutions.com" in cc_header
        assert "comercial@tradingsolutions.com" in cc_header
