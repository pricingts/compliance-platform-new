"""Tests for services/mailer/gmail_client.py — Gmail API transport with DWD.

Contract:
- Uses service account credentials impersonating ``creator_email`` via
  ``Credentials.with_subject`` so the send appears in that user's Sent.
- Returns the Gmail API response dict (at least ``id`` and ``threadId``).
- Translates 401/403 HttpError into :class:`DelegationError` so callers can
  distinguish "DWD is not approved" from transient transport failures.
- Other HttpError classes become :class:`MailerError`.
- MIME is assembled with From/To/Cc/Subject/Message-ID and optional
  In-Reply-To / References headers for RFC 5322 threading.
"""
from __future__ import annotations

import base64
import email
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Disable time.sleep in utils.retry so retry tests run instantly."""
    import utils.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)


def _make_http_error(status: int, body: bytes = b"error"):
    """Build a googleapiclient.errors.HttpError with the given status code.

    We use a minimal mock for ``resp`` that exposes the ``status`` attribute
    the production code reads. Matches the pattern used by
    ``test_google_drive_retry.py``.
    """
    from googleapiclient.errors import HttpError
    resp = MagicMock()
    resp.status = status
    resp.reason = "Test"
    return HttpError(resp, body)


@pytest.fixture
def mock_gmail_build(monkeypatch, mock_streamlit):
    """Patch googleapiclient.discovery.build and service-account Credentials.

    Returns a dict with:
        - ``build``: the MagicMock replacing ``googleapiclient.discovery.build``.
        - ``service``: the service instance returned by ``build(...)``.
        - ``send``: the send method at
          ``service.users().messages().send`` — override ``side_effect`` to
          simulate HttpError.
        - ``creds``: the mock Credentials object (with chainable
          ``.with_subject()``).
        - ``creds_from_info``: the MagicMock replacing
          ``Credentials.from_service_account_info``; inspect ``call_args``
          to verify the scopes passed.
    """
    # Send chain: service.users().messages().send(userId=..., body=...).execute()
    send_mock = MagicMock()
    send_mock.return_value.execute.return_value = {
        "id": "msg-abc",
        "threadId": "thread-xyz",
        "labelIds": ["SENT"],
    }
    service = MagicMock()
    service.users.return_value.messages.return_value.send = send_mock

    build_mock = MagicMock(return_value=service)
    # Patch the name as imported inside gmail_client._build_delegated_service.
    monkeypatch.setattr("googleapiclient.discovery.build", build_mock)

    # with_subject returns self so the chain stays usable.
    creds_mock = MagicMock()
    creds_mock.with_subject.return_value = creds_mock
    from_info_mock = MagicMock(return_value=creds_mock)
    monkeypatch.setattr(
        "google.oauth2.service_account.Credentials.from_service_account_info",
        from_info_mock,
    )

    return {
        "build": build_mock,
        "service": service,
        "send": send_mock,
        "creds": creds_mock,
        "creds_from_info": from_info_mock,
    }


def _decode_raw_from_body(body: dict) -> email.message.Message:
    """Inverse of `_assemble_mime`: decode the base64url payload in the body
    and return the parsed email.message.Message so assertions can inspect
    headers and parts."""
    raw_b64 = body["raw"]
    raw_bytes = base64.urlsafe_b64decode(raw_b64)
    return email.message_from_bytes(raw_bytes)


class TestSendHappyPath:
    def test_send_returns_dict_with_id_and_thread_id(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email

        response = send_email(
            creator_email="creator@tradingsolutions.com",
            to=["client@example.com"],
            cc=None,
            subject="Hola",
            html_body="<p>Hola</p>",
            message_id="<case-C0001-creation@compliance.tradingsolutions.com>",
        )

        assert response["id"] == "msg-abc"
        assert response["threadId"] == "thread-xyz"

    def test_with_subject_is_called_with_creator_email(self, mock_gmail_build):
        """DWD impersonation: Credentials.with_subject must receive the creator."""
        from services.mailer.gmail_client import send_email

        send_email(
            creator_email="alice@tradingsolutions.com",
            to=["client@example.com"],
            cc=None,
            subject="S",
            html_body="<p>x</p>",
            message_id="<case-C0100-creation@compliance.tradingsolutions.com>",
        )

        creds = mock_gmail_build["creds"]
        creds.with_subject.assert_called_once_with("alice@tradingsolutions.com")

    def test_credentials_use_gmail_send_scope(self, mock_gmail_build):
        """Verify the service-account credentials request the gmail.send scope."""
        from services.mailer.gmail_client import GMAIL_SEND_SCOPE, send_email

        send_email(
            creator_email="alice@tradingsolutions.com",
            to=["client@example.com"],
            cc=None,
            subject="S",
            html_body="<p>x</p>",
            message_id="<case-C0101-creation@compliance.tradingsolutions.com>",
        )

        from_info = mock_gmail_build["creds_from_info"]
        _, kwargs = from_info.call_args
        assert kwargs["scopes"] == [GMAIL_SEND_SCOPE]


class TestMimeAssembly:
    def test_mime_includes_from_to_cc_subject_message_id(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email

        send_email(
            creator_email="creator@tradingsolutions.com",
            to=["t1@x.com", "t2@x.com"],
            cc=["cc1@x.com"],
            subject="Asunto bonito",
            html_body="<p>Hola</p>",
            message_id="<case-C0042-creation@compliance.tradingsolutions.com>",
        )

        send = mock_gmail_build["send"]
        _, kwargs = send.call_args
        body = kwargs["body"]
        msg = _decode_raw_from_body(body)

        assert msg["From"] == "creator@tradingsolutions.com"
        assert msg["To"] == "t1@x.com, t2@x.com"
        assert msg["Cc"] == "cc1@x.com"
        assert msg["Subject"] == "Asunto bonito"
        assert (
            msg["Message-ID"]
            == "<case-C0042-creation@compliance.tradingsolutions.com>"
        )

    def test_mime_references_and_in_reply_to_when_provided(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email

        send_email(
            creator_email="creator@tradingsolutions.com",
            to=["t@x.com"],
            cc=None,
            subject="Re:",
            html_body="<p>reply</p>",
            message_id="<msg-2@x>",
            references="<msg-1@x>",
            in_reply_to="<msg-1@x>",
        )

        send = mock_gmail_build["send"]
        _, kwargs = send.call_args
        msg = _decode_raw_from_body(kwargs["body"])
        assert msg["References"] == "<msg-1@x>"
        assert msg["In-Reply-To"] == "<msg-1@x>"

    def test_mime_no_cc_when_none(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email

        send_email(
            creator_email="creator@tradingsolutions.com",
            to=["t@x.com"],
            cc=None,
            subject="S",
            html_body="<p>x</p>",
            message_id="<case-C0001-creation@compliance.tradingsolutions.com>",
        )

        send = mock_gmail_build["send"]
        _, kwargs = send.call_args
        msg = _decode_raw_from_body(kwargs["body"])
        assert msg["Cc"] is None

    def test_mime_no_cc_when_empty_list(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email

        send_email(
            creator_email="creator@tradingsolutions.com",
            to=["t@x.com"],
            cc=[],
            subject="S",
            html_body="<p>x</p>",
            message_id="<case-C0001-creation@compliance.tradingsolutions.com>",
        )

        send = mock_gmail_build["send"]
        _, kwargs = send.call_args
        msg = _decode_raw_from_body(kwargs["body"])
        assert msg["Cc"] is None

    def test_mime_has_html_alternative(self, mock_gmail_build):
        """HTML body is added as an alternative so Gmail renders rich content."""
        from services.mailer.gmail_client import send_email

        send_email(
            creator_email="creator@tradingsolutions.com",
            to=["t@x.com"],
            cc=None,
            subject="S",
            html_body="<p><b>rich</b></p>",
            message_id="<case-C0002-creation@compliance.tradingsolutions.com>",
        )

        send = mock_gmail_build["send"]
        _, kwargs = send.call_args
        msg = _decode_raw_from_body(kwargs["body"])
        # Either a multipart/alternative message, or the HTML payload is reachable.
        payloads = [p.get_content_type() for p in msg.walk()]
        assert "text/html" in payloads


class TestThreadIdBody:
    def test_send_body_includes_thread_id_when_provided(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email

        send_email(
            creator_email="creator@tradingsolutions.com",
            to=["t@x.com"],
            cc=None,
            subject="Re:",
            html_body="<p>r</p>",
            message_id="<msg-2@x>",
            thread_id="thread-xyz",
        )

        send = mock_gmail_build["send"]
        _, kwargs = send.call_args
        assert kwargs["body"].get("threadId") == "thread-xyz"
        assert kwargs["userId"] == "me"

    def test_send_body_omits_thread_id_when_none(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email

        send_email(
            creator_email="creator@tradingsolutions.com",
            to=["t@x.com"],
            cc=None,
            subject="S",
            html_body="<p>x</p>",
            message_id="<msg-1@x>",
        )

        send = mock_gmail_build["send"]
        _, kwargs = send.call_args
        assert "threadId" not in kwargs["body"]


class TestErrorClassification:
    def test_raises_delegation_error_on_401(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email
        from utils.exceptions import DelegationError

        mock_gmail_build["send"].return_value.execute.side_effect = (
            _make_http_error(401, b"Unauthorized")
        )

        with pytest.raises(DelegationError) as exc_info:
            send_email(
                creator_email="alice@tradingsolutions.com",
                to=["t@x.com"],
                cc=None,
                subject="S",
                html_body="<p>x</p>",
                message_id="<msg@x>",
            )

        # Error message mentions the user whose impersonation failed.
        assert "alice@tradingsolutions.com" in str(exc_info.value)

    def test_raises_delegation_error_on_403(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email
        from utils.exceptions import DelegationError

        mock_gmail_build["send"].return_value.execute.side_effect = (
            _make_http_error(403, b"Forbidden")
        )

        with pytest.raises(DelegationError):
            send_email(
                creator_email="alice@tradingsolutions.com",
                to=["t@x.com"],
                cc=None,
                subject="S",
                html_body="<p>x</p>",
                message_id="<msg@x>",
            )

    def test_raises_mailer_error_on_500(self, mock_gmail_build):
        """5xx is classified as MailerError (transient), not DelegationError."""
        from services.mailer.gmail_client import send_email
        from utils.exceptions import DelegationError, MailerError

        mock_gmail_build["send"].return_value.execute.side_effect = (
            _make_http_error(500, b"Internal")
        )

        with pytest.raises(MailerError) as exc_info:
            send_email(
                creator_email="alice@tradingsolutions.com",
                to=["t@x.com"],
                cc=None,
                subject="S",
                html_body="<p>x</p>",
                message_id="<msg@x>",
            )

        # Must NOT be classified as DelegationError (i.e. it's the parent only).
        assert not isinstance(exc_info.value, DelegationError)

    def test_raises_mailer_error_on_400(self, mock_gmail_build):
        from services.mailer.gmail_client import send_email
        from utils.exceptions import DelegationError, MailerError

        mock_gmail_build["send"].return_value.execute.side_effect = (
            _make_http_error(400, b"Bad Request")
        )

        with pytest.raises(MailerError) as exc_info:
            send_email(
                creator_email="alice@tradingsolutions.com",
                to=["t@x.com"],
                cc=None,
                subject="S",
                html_body="<p>x</p>",
                message_id="<msg@x>",
            )
        assert not isinstance(exc_info.value, DelegationError)


class TestMissingCredentials:
    def test_missing_credentials_raises_mailer_error(self, monkeypatch, mock_streamlit):
        """If st.secrets has no google_sheets_credentials AND the env var
        fallback is also empty, the client raises MailerError."""
        from services.mailer.gmail_client import send_email
        from utils.exceptions import MailerError

        # Wipe the service-account secret and the env var fallback.
        del mock_streamlit["secrets"]["google_sheets_credentials"]
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", raising=False)

        with pytest.raises(MailerError):
            send_email(
                creator_email="alice@tradingsolutions.com",
                to=["t@x.com"],
                cc=None,
                subject="S",
                html_body="<p>x</p>",
                message_id="<msg@x>",
            )
