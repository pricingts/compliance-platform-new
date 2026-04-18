"""SMTP transport layer for the compliance platform's mailer.

Responsibilities:
  * Read SMTP credentials lazily (at call time, never at import time) from
    ``st.secrets['smtp']``, falling back to ``SMTP_*`` environment variables.
  * Build an ``email.message.EmailMessage`` with the required headers, incl.
    a deterministic ``Message-ID`` for idempotency.
  * Use ``SMTP_SSL`` for port 465, ``SMTP`` + ``starttls`` for 587.
  * Retry on transient connection-level failures (disconnects, timeouts).
  * Do NOT retry on permanent errors (auth, recipients/sender rejected).
  * Surface every failure as ``utils.exceptions.MailerError`` with the
    original exception chained via ``raise ... from e``.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from services.logging_config import get_logger
from utils.exceptions import MailerError
from utils.retry import with_retry

logger = get_logger(__name__)


# Transient network-level exceptions that are safe to retry.
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    smtplib.SMTPHeloError,
    TimeoutError,
    ConnectionError,
)


def _get_smtp_config() -> dict[str, Any]:
    """Read SMTP config from st.secrets with env-var fallback.

    Looked up at call time (not import time) so the module is importable in
    test environments that don't have Streamlit secrets configured.
    """
    cfg: dict[str, Any] = {}
    try:
        import streamlit as st
        smtp_secrets = st.secrets.get("smtp") if hasattr(st, "secrets") else None
        if smtp_secrets:
            cfg = dict(smtp_secrets)
    except Exception:  # pragma: no cover
        cfg = {}

    cfg.setdefault("host", os.environ.get("SMTP_HOST", ""))
    cfg.setdefault("port", int(os.environ.get("SMTP_PORT", "465")))
    cfg.setdefault("username", os.environ.get("SMTP_USERNAME", ""))
    cfg.setdefault("password", os.environ.get("SMTP_PASSWORD", ""))
    cfg.setdefault(
        "use_tls",
        os.environ.get("SMTP_USE_TLS", "false").lower() in ("1", "true", "yes"),
    )
    cfg.setdefault(
        "from_addr",
        os.environ.get("SMTP_FROM_ADDR", cfg.get("username", "")),
    )

    # Coerce port to int in case it arrived as a string from st.secrets.
    try:
        cfg["port"] = int(cfg["port"])
    except (TypeError, ValueError):
        cfg["port"] = 465

    return cfg


def _build_message(
    *,
    from_addr: str,
    to: list[str],
    cc: list[str],
    subject: str,
    html_body: str,
    message_id: str,
) -> EmailMessage:
    """Build an EmailMessage with the required headers."""
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg.set_content("Este correo requiere un cliente con soporte HTML.")
    msg.add_alternative(html_body, subtype="html")
    return msg


@with_retry(max_attempts=3, exceptions=_RETRYABLE_EXCEPTIONS)
def _transport_send(msg: EmailMessage, cfg: dict[str, Any]) -> None:
    """Inner transport call wrapped in retry for transient failures.

    Permanent errors (auth, recipient refused) are NOT in the retry tuple so
    they propagate after a single attempt.
    """
    host = cfg["host"]
    port = int(cfg["port"])
    username = cfg["username"]
    password = cfg["password"]
    use_tls = bool(cfg.get("use_tls"))

    if port == 465 and not use_tls:
        # Implicit TLS
        with smtplib.SMTP_SSL(host, port) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
    else:
        # STARTTLS (typically port 587)
        with smtplib.SMTP(host, port) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)


def send_email(
    *,
    to: list[str],
    cc: list[str],
    subject: str,
    html_body: str,
    message_id: str,
) -> None:
    """Send an HTML email via SMTP. Raises MailerError on any failure.

    Args:
        to: List of primary recipients. At least one is expected.
        cc: List of CC recipients (may be empty).
        subject: Plain-text subject line.
        html_body: Rendered HTML body.
        message_id: ``<...>`` framed Message-ID header value.

    Raises:
        MailerError: if the SMTP transport fails for any reason. The original
            exception is chained via ``raise ... from``.
    """
    cfg = _get_smtp_config()
    msg = _build_message(
        from_addr=cfg.get("from_addr") or cfg.get("username", ""),
        to=to,
        cc=cc,
        subject=subject,
        html_body=html_body,
        message_id=message_id,
    )
    try:
        _transport_send(msg, cfg)
    except Exception as e:
        logger.error(
            "SMTP send failed",
            extra={
                "exception": f"{type(e).__name__}: {e}",
                "message_id": message_id,
                "to_count": len(to),
                "cc_count": len(cc),
            },
        )
        raise MailerError(f"SMTP send failed: {e}") from e
