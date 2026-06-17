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
from utils.exceptions import DelegationError, MailerError

logger = get_logger(__name__)


__all__ = ["send_request_notification", "validate_mailer_config", "MailerError"]


def _secrets_section(name: str):
    """Return ``st.secrets[name]`` or None, swallowing the usual import/secret
    lookup errors so this is safe to call outside a Streamlit runtime."""
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            return st.secrets.get(name)
    except (ImportError, FileNotFoundError, KeyError, AttributeError):  # pragma: no cover
        return None
    return None


def validate_mailer_config() -> dict:
    """Validate mailer configuration at startup (call once from ``app.py``).

    Does NOT raise — returns a structured result so the caller can surface a
    misconfiguration at deploy/app-load time instead of letting it stay hidden
    until the first request is submitted (the failure mode that left
    notifications silently undelivered). Shape::

        {"enabled": bool, "transport": "gmail"|"smtp", "ok": bool,
         "problems": [str, ...]}

    When the feature flag is off this is a no-op success (``ok=True``,
    ``problems=[]``) because default-off is an intentional state.
    """
    import os

    enabled = _is_feature_enabled()
    transport = _resolve_transport()
    problems: list[str] = []

    if enabled:
        if transport == "gmail":
            creds = _secrets_section("google_sheets_credentials")
            if not creds and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
                problems.append(
                    "transport=gmail but no service-account credentials "
                    "(st.secrets['google_sheets_credentials'] missing and "
                    "GOOGLE_APPLICATION_CREDENTIALS_JSON unset) — Gmail DWD sends "
                    "will fail at send time."
                )
        else:  # smtp
            smtp_cfg = _secrets_section("smtp") or {}
            host = smtp_cfg.get("host") if hasattr(smtp_cfg, "get") else None
            user = smtp_cfg.get("username") if hasattr(smtp_cfg, "get") else None
            pwd = smtp_cfg.get("password") if hasattr(smtp_cfg, "get") else None
            if not (host or os.environ.get("SMTP_HOST")):
                problems.append("transport=smtp but SMTP host is not configured.")
            if not (user or os.environ.get("SMTP_USERNAME")):
                problems.append("transport=smtp but SMTP username is not configured.")
            if not (pwd or os.environ.get("SMTP_PASSWORD")):
                problems.append("transport=smtp but SMTP password is not configured.")

    result = {
        "enabled": enabled,
        "transport": transport,
        "ok": not problems,
        "problems": problems,
    }
    if problems:
        logger.error("Mailer config validation found problems", extra=result)
    return result


def _is_feature_enabled() -> bool:
    """Return True if st.secrets['mailer']['enabled'] is truthy.

    Default-off: if the secret section is missing or the flag is falsy, the
    mailer should not attempt to deliver anything.
    """
    mailer_cfg = None
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            mailer_cfg = st.secrets.get("mailer")
    except (ImportError, FileNotFoundError, KeyError, AttributeError):  # pragma: no cover
        mailer_cfg = None
    if mailer_cfg:
        return bool(mailer_cfg.get("enabled", False))
    # No Streamlit secrets available (e.g. a cron / backfill one-off running
    # outside the app). Fall back to the MAILER_ENABLED env var so operational
    # scripts can enable delivery explicitly. In the Streamlit app, secrets are
    # present, so this branch never changes production behavior.
    import os
    return os.environ.get("MAILER_ENABLED", "").strip().lower() in ("1", "true", "yes")


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
    transport = cfg.get("transport") if cfg else None
    if not transport:
        # No secrets-configured transport (e.g. backfill one-off outside the
        # app) — honor MAILER_TRANSPORT env, else default to smtp.
        import os
        transport = os.environ.get("MAILER_TRANSPORT", "smtp") or "smtp"
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

    try:
        # Threading headers read the email_threads table. A DB/session error
        # here previously escaped send_request_notification as an opaque
        # exception (it ran BEFORE this try). Keeping it inside the try and
        # converting any failure to MailerError means the row stays
        # un-notified (email_notified_at NULL) so the retry sweep re-attempts,
        # instead of looking like a hard crash to the form.
        try:
            references, in_reply_to, thread_id = _build_threading_headers(
                session, request_id
            )
        except MailerError:
            raise
        except Exception as e:  # noqa: BLE001 - DB/session error reading thread
            raise MailerError(
                f"threading-headers read failed for {case_id}: {e}"
            ) from e

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
    except DelegationError:
        # Permanent: Gmail DWD is not authorized for this creator. Log loudly
        # with creator + case so an operator can fix the scope in Google Admin
        # Console; leave the row un-notified so the retry sweep redelivers once
        # delegation is fixed.
        logger.critical(
            "send_request_notification: Gmail delegation failed — authorize "
            "DWD in Admin Console; retry sweep will redeliver",
            extra={
                "case_id": case_id,
                "request_id": request_id,
                "creator_email": creator_email,
            },
        )
        raise
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
