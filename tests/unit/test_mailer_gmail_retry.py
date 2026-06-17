"""Tests for the Gmail transport retry policy (services/mailer/gmail_client.py).

Transient Gmail API errors (5xx / 429) must be retried (mirroring SMTP), while
DelegationError (401/403 — a permanent DWD misconfiguration) must propagate on
the first attempt without retrying.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class _FakeResp:
    def __init__(self, status):
        self.status = status
        self.reason = "error"


def _http_error(status):
    from googleapiclient.errors import HttpError
    return HttpError(_FakeResp(status), b"{}")


@pytest.fixture
def _no_sleep(monkeypatch):
    import utils.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)


def _patch_service(monkeypatch, execute_side_effect):
    """Make gmail_client._build_delegated_service return a mock whose
    send().execute() uses the given side_effect; return the execute mock."""
    from services.mailer import gmail_client

    service = MagicMock()
    execute = service.users.return_value.messages.return_value.send.return_value.execute
    execute.side_effect = execute_side_effect
    monkeypatch.setattr(gmail_client, "_build_delegated_service", lambda _email: service)
    return execute


def _send(**over):
    from services.mailer import gmail_client
    kwargs = dict(
        creator_email="pedro@tradingsolutions.com",
        to=["compliance@tradingsolutions.com"],
        subject="Solicitud de Registro - C0042 - Acme",
        html_body="<p>hi</p>",
        message_id="<case-C0042-creation@compliance.tradingsolutions.com>",
    )
    kwargs.update(over)
    return gmail_client.send_email(**kwargs)


class TestGmailRetry:
    def test_retries_transient_then_succeeds(self, monkeypatch, _no_sleep):
        execute = _patch_service(
            monkeypatch,
            [_http_error(503), {"id": "m1", "threadId": "t1"}],
        )
        resp = _send()
        assert resp["threadId"] == "t1"
        assert execute.call_count == 2  # one failure + one success

    def test_gives_up_after_max_attempts_on_persistent_transient(
        self, monkeypatch, _no_sleep
    ):
        from utils.exceptions import TransientMailerError

        execute = _patch_service(monkeypatch, _http_error(429))  # always 429
        with pytest.raises(TransientMailerError):
            _send()
        assert execute.call_count == 3  # max_attempts

    def test_delegation_error_is_not_retried(self, monkeypatch, _no_sleep):
        from utils.exceptions import DelegationError

        execute = _patch_service(monkeypatch, _http_error(403))
        with pytest.raises(DelegationError):
            _send()
        assert execute.call_count == 1  # permanent: no retry
