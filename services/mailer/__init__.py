"""Mailer package — composes template + recipients + transport.

Public entry point:
    from services.mailer import send_request_notification

The top-level ``send_request_notification`` is the only function forms/views
should call. It handles:
  * Feature-flag gating (``st.secrets['mailer']['enabled']``).
  * Transport selection via ``st.secrets['mailer']['transport']`` (``'smtp'``
    or ``'gmail'``). Default: ``'smtp'`` for backward-compat.
  * Idempotency (skip if ``requests.email_notified_at`` is already set).
  * Recipient resolution.
  * HTML rendering.
  * RFC 5322 threading headers (``References``, ``In-Reply-To``) and the
    Gmail ``threadId`` for subsequent emails on a case.
  * Transport delivery with retry (SMTP) or DWD impersonation (Gmail).
  * Persisting the ``email_threads`` row so future events (reminders, status
    changes) on the same case thread into the same Gmail conversation.
  * Marking the request row as notified on success.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.crud.clientes import get_request_by_case_id
from services.logging_config import get_logger
from services.mailer import smtp_client
from services.mailer.recipients import resolve_recipients
from services.mailer.templates import render_request_email
from utils.exceptions import MailerError

logger = get_logger(__name__)


__all__ = ["send_request_notification", "MailerError"]


def _is_feature_enabled() -> bool:
    """Return True if st.secrets['mailer']['enabled'] is truthy.

    Default-off: if the secret section is missing or the flag is falsy, the
    mailer should not attempt to deliver anything.
    """
    try:
        import streamlit as st
        mailer_cfg = st.secrets.get("mailer") if hasattr(st, "secrets") else None
    except (ImportError, FileNotFoundError, KeyError, AttributeError):  # pragma: no cover
        # Streamlit missing or secrets not loaded — treat feature as disabled.
        return False
    if not mailer_cfg:
        return False
    return bool(mailer_cfg.get("enabled", False))


def _resolve_transport() -> str:
    """Return ``'gmail'`` or ``'smtp'`` based on ``st.secrets['mailer']['transport']``.

    Default: ``'smtp'`` (backward-compat during the Phase 8 rollout). Unknown
    values fall back to ``'smtp'`` with a logger warning so misconfiguration
    is visible but non-fatal.
    """
    cfg: Any = None
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            cfg = st.secrets.get("mailer")
    except (ImportError, FileNotFoundError, KeyError, AttributeError):  # pragma: no cover
        cfg = None
    transport = "smtp"
    if cfg:
        transport = cfg.get("transport", "smtp") or "smtp"
    if transport not in ("smtp", "gmail"):
        logger.warning(
            "Unknown mailer.transport=%r, falling back to smtp", transport
        )
        return "smtp"
    return transport


def _build_threading_headers(
    session: Session, request_id: int
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return ``(references, in_reply_to, thread_id)`` for the next email.

    * For the FIRST event (creation) there is no ``email_threads`` row yet
      and the tuple is ``(None, None, None)``.
    * For SUBSEQUENT events (reminders, status changes) the existing row is
      read and we construct:
        - ``references`` = ``(stored_chain + " " + stored_last_message_id).strip()``
        - ``in_reply_to`` = ``stored_last_message_id``
        - ``thread_id``   = ``stored_gmail_thread_id`` (may be ``None`` if the
          first event was sent via SMTP before the Gmail migration).
    """
    from database.crud.email_threads import get_thread_by_request_id

    existing = get_thread_by_request_id(session, request_id)
    if existing is None:
        return (None, None, None)
    chain = (existing.get("references_chain") or "").strip()
    last = existing.get("last_message_id") or ""
    references: Optional[str]
    if chain or last:
        references = f"{chain} {last}".strip()
    else:
        references = None
    return (references, last or None, existing.get("gmail_thread_id"))


def _build_message_id(case_id: str) -> str:
    """Deterministic Message-ID for the creation notification."""
    return f"<case-{case_id}-creation@compliance.tradingsolutions.com>"


def _mark_notified(session: Session, request_id: int) -> None:
    """Set ``requests.email_notified_at`` to NOW on both Postgres and SQLite."""
    dialect = session.bind.dialect.name if session.bind else "unknown"
    if dialect == "postgresql":
        session.execute(
            text("UPDATE requests SET email_notified_at = NOW() WHERE id = :id"),
            {"id": request_id},
        )
    else:
        session.execute(
            text(
                "UPDATE requests SET email_notified_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {"id": request_id},
        )
    session.commit()


def send_request_notification(
    session: Session,
    case_id: str,
    payload: dict[str, Any],
    creator_email: str,
    submitted_by_email: Optional[str] = None,
) -> bool:
    """Send the "new request" notification email for ``case_id``.

    Contract:
      * Returns ``False`` (and skips sending) when either:
          - The mailer feature flag is disabled.
          - ``email_notified_at`` is already set for the target request.
      * Returns ``True`` when the email was sent AND the row was marked.
      * Raises :class:`MailerError` on transport failure; in that case the
        row is NOT marked so a later retry can still deliver the message.
    """
    if not _is_feature_enabled():
        logger.info(
            "Mailer feature flag disabled — skipping notification",
            extra={"case_id": case_id},
        )
        return False

    request = get_request_by_case_id(session, case_id)
    if request is None:
        logger.error(
            "send_request_notification: request not found for case_id",
            extra={"case_id": case_id},
        )
        return False

    request_id = request["id"]

    # Idempotency guard: pull the latest email_notified_at directly.
    notified_at = session.execute(
        text("SELECT email_notified_at FROM requests WHERE id = :id"),
        {"id": request_id},
    ).scalar()
    if notified_at is not None:
        logger.info(
            "send_request_notification: already notified, skipping",
            extra={"case_id": case_id, "request_id": request_id},
        )
        return False

    # Resolve transport first — its value decides whether creator should be
    # removed from CC (creator is From when transport == 'gmail', so having
    # them in CC too would double up in the recipient's client).
    transport = _resolve_transport()

    recipients = resolve_recipients(
        session=session,
        creator_email=creator_email,
        submitted_by_email=submitted_by_email,
        exclude_creator_from_cc=(transport == "gmail"),
    )
    if not recipients["to"]:
        logger.error(
            "send_request_notification: no TO recipients — cannot send",
            extra={"case_id": case_id},
        )
        return False

    subject, html_body = render_request_email(
        case_id,
        payload,
        creator_email=creator_email,
        submitted_by_email=submitted_by_email,
    )
    message_id = _build_message_id(case_id)

    references, in_reply_to, thread_id = _build_threading_headers(
        session, request_id
    )

    try:
        if transport == "gmail":
            from services.mailer import gmail_client
            response = gmail_client.send_email(
                creator_email=creator_email,
                to=recipients["to"],
                cc=recipients["cc"] or None,
                subject=subject,
                html_body=html_body,
                message_id=message_id,
                thread_id=thread_id,
                references=references,
                in_reply_to=in_reply_to,
            )
            gmail_thread_id = response.get("threadId")
        else:
            smtp_client.send_email(
                to=recipients["to"],
                cc=recipients["cc"],
                subject=subject,
                html_body=html_body,
                message_id=message_id,
            )
            gmail_thread_id = None
    except MailerError:
        # Already logged inside the transport. Re-raise so the caller can decide.
        raise

    # Persist the thread row BEFORE marking notified so a failure here doesn't
    # leave a request "notified" without a corresponding thread entry. Any
    # exception is logged but swallowed — the email already shipped and we
    # don't want to raise and drop the notified-at update on the floor.
    try:
        from database.crud.email_threads import upsert_thread
        upsert_thread(
            session=session,
            request_id=request_id,
            gmail_thread_id=gmail_thread_id,
            last_message_id=message_id,
            references_chain=references,
        )
    except Exception:  # pragma: no cover - defensive: never block delivery ack
        logger.exception(
            "Failed to persist email_threads row",
            extra={"case_id": case_id, "request_id": request_id},
        )

    _mark_notified(session, request_id)
    logger.info(
        "send_request_notification: sent",
        extra={
            "case_id": case_id,
            "request_id": request_id,
            "to_count": len(recipients["to"]),
            "cc_count": len(recipients["cc"]),
            "transport": transport,
            "gmail_thread_id": gmail_thread_id,
        },
    )
    return True
