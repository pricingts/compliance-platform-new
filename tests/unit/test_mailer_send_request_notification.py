"""Tests for services/mailer/__init__.py::send_request_notification.

Contract:
- Feature flag gate: mailer["enabled"] must be truthy or return False + skip.
- Idempotency: if email_notified_at is already set, return False + skip.
- Success path: send email, mark notified, return True.
- Failure path: SMTP error → raise MailerError, do NOT mark notified.
- Message-ID is deterministic: <case-{CASE}-creation@compliance.tradingsolutions.com>.
- TO/CC resolution integrates with resolve_recipients().
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


def _seed_request(db_session, seed_profiles, case_id="C0042"):
    """Insert a requests row that satisfies get_request_by_case_id."""
    db_session.execute(
        text(
            """
            INSERT INTO requests (profile_id, company_name, user_email, case_id)
            VALUES (:pid, :company, :email, :case_id)
            """
        ),
        {
            "pid": seed_profiles["cliente"],
            "company": "Acme Corp",
            "email": "pedro@tradingsolutions.com",
            "case_id": case_id,
        },
    )
    db_session.commit()
    return db_session.execute(
        text("SELECT id FROM requests WHERE case_id = :c"),
        {"c": case_id},
    ).scalar()


class TestSendRequestNotification:
    def test_skips_when_feature_flag_disabled(
        self, db_session, seed_profiles, mock_smtp
    ):
        from services.mailer import send_request_notification

        _seed_request(db_session, seed_profiles)
        mock_smtp["secrets"]["mailer"] = {"enabled": False}

        result = send_request_notification(
            session=db_session,
            case_id="C0042",
            payload={"company_name": "Acme Corp"},
            creator_email="pedro@tradingsolutions.com",
        )

        assert result is False
        # SMTP was not touched
        assert not mock_smtp["instance_ssl"].send_message.called

    def test_skips_when_already_notified(
        self, db_session, seed_profiles, mock_smtp
    ):
        from services.mailer import send_request_notification

        rid = _seed_request(db_session, seed_profiles)
        db_session.execute(
            text(
                "UPDATE requests SET email_notified_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {"id": rid},
        )
        db_session.commit()

        result = send_request_notification(
            session=db_session,
            case_id="C0042",
            payload={"company_name": "Acme Corp"},
            creator_email="pedro@tradingsolutions.com",
        )
        assert result is False
        assert not mock_smtp["instance_ssl"].send_message.called

    def test_sends_and_marks_notified_on_success(
        self, db_session, seed_profiles, mock_smtp
    ):
        from services.mailer import send_request_notification

        rid = _seed_request(db_session, seed_profiles)

        result = send_request_notification(
            session=db_session,
            case_id="C0042",
            payload={"company_name": "Acme Corp"},
            creator_email="pedro@tradingsolutions.com",
        )

        assert result is True
        assert mock_smtp["instance_ssl"].send_message.called

        notified = db_session.execute(
            text("SELECT email_notified_at FROM requests WHERE id = :id"),
            {"id": rid},
        ).scalar()
        assert notified is not None

    def test_raises_mailer_error_on_smtp_failure(
        self, db_session, seed_profiles, mock_smtp, monkeypatch
    ):
        import smtplib

        from services.mailer import send_request_notification
        from utils.exceptions import MailerError

        # Also disable retry sleep.
        import utils.retry as retry_mod
        monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)

        rid = _seed_request(db_session, seed_profiles)
        mock_smtp["instance_ssl"].login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"auth failed"
        )

        with pytest.raises(MailerError):
            send_request_notification(
                session=db_session,
                case_id="C0042",
                payload={"company_name": "Acme Corp"},
                creator_email="pedro@tradingsolutions.com",
            )

        # email_notified_at must NOT be set on failure.
        notified = db_session.execute(
            text("SELECT email_notified_at FROM requests WHERE id = :id"),
            {"id": rid},
        ).scalar()
        assert notified is None

    def test_uses_deterministic_message_id(
        self, db_session, seed_profiles, mock_smtp
    ):
        from services.mailer import send_request_notification

        _seed_request(db_session, seed_profiles, case_id="C0042")

        send_request_notification(
            session=db_session,
            case_id="C0042",
            payload={"company_name": "Acme Corp"},
            creator_email="pedro@tradingsolutions.com",
        )

        sent_msg = mock_smtp["instance_ssl"].send_message.call_args[0][0]
        assert (
            sent_msg["Message-ID"]
            == "<case-C0042-creation@compliance.tradingsolutions.com>"
        )

    def test_sends_with_correct_to_and_cc(
        self, db_session, seed_profiles, mock_smtp
    ):
        from services.mailer import send_request_notification

        # Seed 1 active compliance user so we exercise the dynamic path.
        db_session.execute(
            text(
                """
                INSERT INTO users (email, nombre_display, rol, activo)
                VALUES ('extra@tradingsolutions.com', 'Extra Compliance', 'compliance', 1)
                """
            )
        )
        db_session.commit()

        _seed_request(db_session, seed_profiles, case_id="C0042")

        send_request_notification(
            session=db_session,
            case_id="C0042",
            payload={"company_name": "Acme Corp"},
            creator_email="pedro@tradingsolutions.com",
            submitted_by_email="is@tradingsolutions.com",
        )

        sent_msg = mock_smtp["instance_ssl"].send_message.call_args[0][0]
        # TO has the hardcoded defaults + the dynamic user
        to_header = sent_msg["To"]
        assert "compliance1@tradingsolutions.com" in to_header
        assert "compliance2@tradingsolutions.com" in to_header
        assert "compliance@tradingsolutions.com" in to_header
        assert "extra@tradingsolutions.com" in to_header
        # CC has creator + submitted_by
        cc_header = sent_msg["Cc"]
        assert "pedro@tradingsolutions.com" in cc_header
        assert "is@tradingsolutions.com" in cc_header
