"""Tests for services/mailer/smtp_client.py — SMTP send logic.

Contract:
- Uses SMTP_SSL on port 465.
- Uses SMTP + starttls on port 587 when use_tls is True.
- Raises MailerError on SMTP exceptions.
- Authentication errors are NOT retried (permanent).
- Message-ID header is set on the outgoing email.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Disable time.sleep in utils.retry so retry tests run instantly."""
    import utils.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)


class TestSendEmail:
    def test_send_email_uses_ssl_when_port_465(self, mock_smtp):
        from services.mailer.smtp_client import send_email

        mock_smtp["secrets"]["smtp"]["port"] = 465
        mock_smtp["secrets"]["smtp"]["use_tls"] = False

        send_email(
            to=["a@tradingsolutions.com"],
            cc=[],
            subject="Subject",
            html_body="<p>Hi</p>",
            message_id="<case-C0001-creation@compliance.tradingsolutions.com>",
        )

        # SMTP_SSL was used, plain SMTP was not
        assert mock_smtp["ssl"].called, "Expected smtplib.SMTP_SSL to be used for port 465"
        assert not mock_smtp["plain"].called

    def test_send_email_uses_starttls_when_port_587_and_use_tls(self, mock_smtp):
        from services.mailer.smtp_client import send_email

        mock_smtp["secrets"]["smtp"]["port"] = 587
        mock_smtp["secrets"]["smtp"]["use_tls"] = True

        send_email(
            to=["a@tradingsolutions.com"],
            cc=[],
            subject="Subject",
            html_body="<p>Hi</p>",
            message_id="<case-C0001-creation@compliance.tradingsolutions.com>",
        )

        assert mock_smtp["plain"].called, "Expected smtplib.SMTP for port 587"
        # starttls must be called
        assert mock_smtp["instance_plain"].starttls.called
        assert not mock_smtp["ssl"].called

    def test_send_email_raises_mailer_error_on_smtp_exception(self, mock_smtp):
        import smtplib

        from services.mailer.smtp_client import send_email
        from utils.exceptions import MailerError

        # Make login fail with a non-retryable error so the error surfaces after one attempt.
        mock_smtp["instance_ssl"].login.side_effect = smtplib.SMTPRecipientsRefused({})

        with pytest.raises(MailerError):
            send_email(
                to=["a@tradingsolutions.com"],
                cc=[],
                subject="Subject",
                html_body="<p>Hi</p>",
                message_id="<case-C0001-creation@compliance.tradingsolutions.com>",
            )

    def test_send_email_does_not_retry_on_authentication_error(self, mock_smtp):
        import smtplib

        from services.mailer.smtp_client import send_email
        from utils.exceptions import MailerError

        # SMTPAuthenticationError is a permanent failure — no retries.
        mock_smtp["instance_ssl"].login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"auth failed"
        )

        with pytest.raises(MailerError):
            send_email(
                to=["a@tradingsolutions.com"],
                cc=[],
                subject="Subject",
                html_body="<p>Hi</p>",
                message_id="<case-C0001-creation@compliance.tradingsolutions.com>",
            )

        # Login should have been called exactly once (no retries).
        assert mock_smtp["instance_ssl"].login.call_count == 1

    def test_send_email_sets_message_id_header(self, mock_smtp):
        from services.mailer.smtp_client import send_email

        msg_id = "<case-C0042-creation@compliance.tradingsolutions.com>"
        send_email(
            to=["a@tradingsolutions.com"],
            cc=["cc@tradingsolutions.com"],
            subject="Subject",
            html_body="<p>Hi</p>",
            message_id=msg_id,
        )

        assert mock_smtp["instance_ssl"].send_message.called
        sent_msg = mock_smtp["instance_ssl"].send_message.call_args[0][0]
        assert sent_msg["Message-ID"] == msg_id
        assert sent_msg["Subject"] == "Subject"
        assert sent_msg["To"] == "a@tradingsolutions.com"
        assert sent_msg["Cc"] == "cc@tradingsolutions.com"
