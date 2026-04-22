"""Gmail API transport for the compliance mailer.

Uses service account credentials (the same ones Drive/Sheets use) with
Domain-Wide Delegation (DWD) to impersonate the user who created the
request. The email is sent via ``gmail.users().messages().send`` with
``userId='me'``, which resolves to the impersonated user, so the sent
message appears in THAT user's Sent folder and the ``From`` header is
``<creator>``.

Prerequisite (one-time, in Google Admin Console):
  * Delegate the service-account client_id with scope
    ``https://www.googleapis.com/auth/gmail.send``.

If DWD has not been approved for the target user, Gmail returns a 401/403
``HttpError``; we translate those into :class:`DelegationError` with a
message naming the user so operators can verify the scope is authorized
for the service-account client_id in Admin Console. The caller can then
decide whether to fall back to the SMTP transport.
"""
from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any, Optional

from services.logging_config import get_logger
from utils.exceptions import DelegationError, MailerError

logger = get_logger(__name__)

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def _load_service_account_info() -> dict[str, Any]:
    """Return the service-account dict from ``st.secrets`` or env fallback.

    Reads ``st.secrets['google_sheets_credentials']`` (the same key
    ``services/sheets_writer.py`` uses) so a single credential powers
    Drive / Sheets / Gmail. Falls back to
    ``GOOGLE_APPLICATION_CREDENTIALS_JSON`` (a JSON string) for CI and
    smoke scripts that don't have Streamlit configured.
    """
    raw: Any = None
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            raw = st.secrets.get("google_sheets_credentials")
    except (ImportError, FileNotFoundError, KeyError, AttributeError):  # pragma: no cover
        raw = None

    if not raw:
        import json
        import os
        env_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if env_json:
            try:
                raw = json.loads(env_json)
            except json.JSONDecodeError as e:
                raise MailerError(
                    "GOOGLE_APPLICATION_CREDENTIALS_JSON is not valid JSON."
                ) from e

    if not raw:
        raise MailerError(
            "No service account credentials available "
            "(st.secrets['google_sheets_credentials'] missing and "
            "GOOGLE_APPLICATION_CREDENTIALS_JSON is unset)."
        )
    # dict(raw) works both for plain dict and for Streamlit's AttrDict.
    return dict(raw)


def _build_delegated_service(creator_email: str):
    """Build a Gmail service client impersonating ``creator_email`` via DWD."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    info = _load_service_account_info()
    credentials = Credentials.from_service_account_info(
        info,
        scopes=[GMAIL_SEND_SCOPE],
    ).with_subject(creator_email)
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _assemble_mime(
    *,
    creator_email: str,
    to: list[str],
    cc: Optional[list[str]],
    subject: str,
    html_body: str,
    message_id: str,
    references: Optional[str],
    in_reply_to: Optional[str],
) -> str:
    """Build the MIME message and return it base64url-encoded for Gmail API.

    Plain-text fallback is set first, then the HTML alternative, so the
    resulting message is ``multipart/alternative`` and Gmail renders the
    HTML part for the recipient.
    """
    msg = EmailMessage()
    msg["From"] = creator_email
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    if references:
        msg["References"] = references
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    # Plain-text fallback then HTML alternative (Gmail renders HTML).
    msg.set_content("Este correo requiere un cliente con soporte HTML.")
    msg.add_alternative(html_body, subtype="html")
    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")


def _send_via_gmail(
    creator_email: str,
    raw_b64: str,
    thread_id: Optional[str],
) -> dict[str, Any]:
    """Do the Gmail API send call and classify ``HttpError`` responses.

    4xx responses specific to delegation (401 / 403) become
    :class:`DelegationError`; every other ``HttpError`` is wrapped in
    :class:`MailerError` with the upstream status code. Transient 5xx and
    429 become ``MailerError`` too — the caller decides whether to retry
    or fall back to SMTP.
    """
    from googleapiclient.errors import HttpError

    service = _build_delegated_service(creator_email)
    body: dict[str, Any] = {"raw": raw_b64}
    if thread_id:
        body["threadId"] = thread_id
    try:
        response = service.users().messages().send(userId="me", body=body).execute()
        return response
    except HttpError as e:
        status = getattr(e.resp, "status", None)
        if status in (401, 403):
            raise DelegationError(
                f"Gmail API rejected impersonation for {creator_email}. "
                f"Verify DWD scope '{GMAIL_SEND_SCOPE}' is authorized for "
                "the service account client_id in Google Admin Console."
            ) from e
        if status in (500, 502, 503, 504, 429):
            raise MailerError(
                f"Gmail API transient error ({status}): {e}"
            ) from e
        raise MailerError(f"Gmail API error ({status}): {e}") from e


def send_email(
    *,
    creator_email: str,
    to: list[str],
    cc: Optional[list[str]] = None,
    subject: str,
    html_body: str,
    message_id: str,
    thread_id: Optional[str] = None,
    references: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> dict[str, Any]:
    """Send an email via the Gmail API, impersonating ``creator_email``.

    Args:
        creator_email: The user to impersonate; appears as ``From`` and
            owns the sent message. Must be authorized via DWD.
        to: Primary recipients.
        cc: Optional CC recipients. ``None`` or ``[]`` omits the header.
        subject: Plain-text subject line.
        html_body: Rendered HTML body; Gmail clients render it.
        message_id: RFC 5322 ``Message-ID`` header value, including the
            surrounding angle brackets.
        thread_id: Optional Gmail ``threadId`` for server-side grouping so
            replies land in the same conversation.
        references: Optional RFC 5322 ``References`` chain.
        in_reply_to: Optional RFC 5322 ``In-Reply-To`` header.

    Returns:
        The Gmail API response dict containing at least ``id`` and
        ``threadId``.

    Raises:
        DelegationError: 401/403 from Gmail API (DWD misconfigured or
            scope missing for the target user).
        MailerError: any other transport or API failure.
    """
    raw_b64 = _assemble_mime(
        creator_email=creator_email,
        to=to,
        cc=cc,
        subject=subject,
        html_body=html_body,
        message_id=message_id,
        references=references,
        in_reply_to=in_reply_to,
    )
    response = _send_via_gmail(creator_email, raw_b64, thread_id)
    logger.info(
        "gmail.send: ok",
        extra={
            "creator": creator_email,
            "to_count": len(to),
            "cc_count": len(cc or []),
            "message_id": message_id,
            "gmail_message_id": response.get("id"),
            "gmail_thread_id": response.get("threadId"),
        },
    )
    return response
