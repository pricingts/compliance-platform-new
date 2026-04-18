"""Mailer package — composes template + recipients + SMTP transport.

Public entry point:
    from services.mailer import send_request_notification

The top-level ``send_request_notification`` is the only function forms/views
should call. It handles:
  * Feature-flag gating (``st.secrets['mailer']['enabled']``).
  * Idempotency (skip if ``requests.email_notified_at`` is already set).
  * Recipient resolution.
  * HTML rendering.
  * SMTP delivery with retry.
  * Marking the request row as notified on success.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.crud.clientes import get_request_by_case_id
from services.logging_config import get_logger
from services.mailer.recipients import resolve_recipients
from services.mailer.smtp_client import send_email
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
    except Exception:  # pragma: no cover
        return False
    if not mailer_cfg:
        return False
    return bool(mailer_cfg.get("enabled", False))


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
      * Raises :class:`MailerError` on SMTP failure; in that case the row is
        NOT marked so a later retry can still deliver the message.
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

    # Idempotency guard: pull the latest email_notified_at directly.
    notified_at = session.execute(
        text("SELECT email_notified_at FROM requests WHERE id = :id"),
        {"id": request["id"]},
    ).scalar()
    if notified_at is not None:
        logger.info(
            "send_request_notification: already notified, skipping",
            extra={"case_id": case_id, "request_id": request["id"]},
        )
        return False

    recipients = resolve_recipients(
        session=session,
        creator_email=creator_email,
        submitted_by_email=submitted_by_email,
    )
    if not recipients["to"]:
        logger.error(
            "send_request_notification: no TO recipients — cannot send",
            extra={"case_id": case_id},
        )
        return False

    subject, html_body = render_request_email(case_id, payload)
    message_id = _build_message_id(case_id)

    try:
        send_email(
            to=recipients["to"],
            cc=recipients["cc"],
            subject=subject,
            html_body=html_body,
            message_id=message_id,
        )
    except MailerError:
        # Already logged inside send_email. Re-raise so the caller can decide.
        raise

    _mark_notified(session, request["id"])
    logger.info(
        "send_request_notification: sent",
        extra={
            "case_id": case_id,
            "request_id": request["id"],
            "to_count": len(recipients["to"]),
            "cc_count": len(recipients["cc"]),
        },
    )
    return True
