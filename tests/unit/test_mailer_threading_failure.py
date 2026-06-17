"""Fix C: a DB error while building threading headers must be treated as a
(retryable) notification failure — raised as MailerError and leaving
email_notified_at NULL — not leak out as an opaque exception.

Previously _build_threading_headers ran BEFORE the transport try block, so a
session/DB error there escaped send_request_notification entirely.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


def _seed_request(db_session, seed_profiles, case_id="C0042"):
    db_session.execute(
        text(
            "INSERT INTO requests (profile_id, company_name, user_email, case_id) "
            "VALUES (:pid, 'Acme Corp', 'pedro@tradingsolutions.com', :c)"
        ),
        {"pid": seed_profiles["cliente"], "c": case_id},
    )
    db_session.commit()
    return db_session.execute(
        text("SELECT id FROM requests WHERE case_id = :c"), {"c": case_id}
    ).scalar()


def test_threading_header_db_error_becomes_mailer_error_and_leaves_null(
    db_session, seed_profiles, mock_smtp, monkeypatch
):
    from services.mailer import send_request_notification
    from utils.exceptions import MailerError
    import database.crud.email_threads as et

    rid = _seed_request(db_session, seed_profiles)

    def _boom(_session, _request_id):
        raise RuntimeError("simulated DB/session failure reading email_threads")

    monkeypatch.setattr(et, "get_thread_by_request_id", _boom)

    with pytest.raises(MailerError):
        send_request_notification(
            session=db_session,
            case_id="C0042",
            payload={"company_name": "Acme Corp"},
            creator_email="pedro@tradingsolutions.com",
        )

    # Must NOT be marked notified -> the retry sweep can redeliver.
    notified = db_session.execute(
        text("SELECT email_notified_at FROM requests WHERE id = :id"), {"id": rid}
    ).scalar()
    assert notified is None
    # And the transport was never reached.
    assert not mock_smtp["instance_ssl"].send_message.called
