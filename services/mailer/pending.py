"""Durable redelivery of compliance creation-notifications.

The creation notification (``services.mailer.send_request_notification``) is a
best-effort step fired right after a request is saved. If it is interrupted
(e.g. a Streamlit rerun preempts the script on a double-submit) or hits a
transient transport error, the request persists with ``email_notified_at IS
NULL`` and the email is silently lost — there is no second attempt.

This module closes that gap:

* :func:`build_payload_from_request` reconstructs the notification payload
  (and creator / submitted-by / case_id) from the persisted ``requests`` row
  plus its child registration tables — so a notification can be re-sent later,
  outside the original form request, with the same content.
* :func:`retry_pending_notifications` sweeps requests that were never notified
  and re-invokes ``send_request_notification`` for each. The send is idempotent
  (it skips rows whose ``email_notified_at`` is already set), so the sweep is
  safe to run repeatedly (on app load and/or from a scheduled job).

Only rows in the *mailer era* are considered: the cutoff is the smallest id
that has ever been notified (``MIN(id) WHERE email_notified_at IS NOT NULL``).
Rows older than that predate the Python mailer (they were handled by the legacy
Google Sheets Apps Script notifier) and must NOT be re-sent.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.logging_config import get_logger
from utils.exceptions import MailerError

logger = get_logger(__name__)


def _mailer_era_min_id(session: Session) -> Optional[int]:
    """Smallest request id that has ever been notified, or None if none have.

    This is the boundary between the legacy (pre-Python-mailer) rows — which
    must never be re-sent — and the mailer era.
    """
    return session.execute(
        text("SELECT MIN(id) FROM requests WHERE email_notified_at IS NOT NULL")
    ).scalar()


def build_payload_from_request(
    session: Session, request_id: int
) -> Optional[dict[str, Any]]:
    """Reconstruct the notification inputs for ``request_id`` from the DB.

    Returns ``{"case_id", "payload", "creator_email", "submitted_by_email"}``
    shaped exactly like the dict the form assembles at creation time (the keys
    mirror ``services.mailer.templates._FIELD_MAP``), or ``None`` if the request
    does not exist or has no ``case_id``.
    """
    row = session.execute(
        text(
            """
            SELECT r.id, r.case_id, r.company_name, r.email, r.trading,
                   r.country, r.language, r.reminder_frequency, r.operation_type,
                   r.commodity, r.has_customs, r.has_port, r.has_shipping_line,
                   r.commercial, r.user_email, r.submitted_by_email, r.notes,
                   p.name AS tipo_solicitud
              FROM requests r
              LEFT JOIN profiles p ON p.id = r.profile_id
             WHERE r.id = :rid
            """
        ),
        {"rid": request_id},
    ).fetchone()
    if not row:
        return None
    r = row._mapping
    if not r["case_id"]:
        return None

    # ---- Child registrations -> display strings (mirror _build_email_payload).
    customs = [
        x[0]
        for x in session.execute(
            text(
                "SELECT customs_name FROM customs_registration "
                "WHERE request_id = :rid"
            ),
            {"rid": request_id},
        ).fetchall()
    ]
    ports = [
        x[0]
        for x in session.execute(
            text(
                "SELECT DISTINCT port_name FROM port_registration "
                "WHERE request_id = :rid"
            ),
            {"rid": request_id},
        ).fetchall()
    ]
    lines = session.execute(
        text(
            "SELECT line_name, pol, pod, product, container_type, shipper_bl "
            "FROM shipping_line_registration WHERE request_id = :rid"
        ),
        {"rid": request_id},
    ).fetchall()

    def _flag_value(items: list, flag: Any) -> str:
        if items:
            return ", ".join([str(i) for i in items])
        return "Sí" if flag else ""

    line_names = [ln[0] for ln in lines]
    msc = next((ln for ln in lines if (ln[0] or "").upper() == "MSC"), None)

    payload = {
        "case_id": r["case_id"] or "",
        "requested_by": r["commercial"] or "",
        "tipo_solicitud": r["tipo_solicitud"] or "",
        "company_name": r["company_name"] or "",
        "email": r["email"] or "",
        "trading": r["trading"] or "",
        "location": r["country"] or "",
        "language": r["language"] or "",
        "reminder_frequency": r["reminder_frequency"] or "",
        "tipo_operacion": r["operation_type"] or "",
        "commodity": r["commodity"] or "",
        "aduana": _flag_value(customs, r["has_customs"]),
        "puerto": _flag_value(ports, r["has_port"]),
        "linea_naviera": _flag_value(line_names, r["has_shipping_line"]),
        "pol": (msc[1] if msc else "") or "",
        "pod": (msc[2] if msc else "") or "",
        "producto": (msc[3] if msc else "") or "",
        "tipo_contenedor": (msc[4] if msc else "") or "",
        "shipper_bl": (msc[5] if msc else "") or "",
        "notes": r["notes"] or "",
    }

    # creator_email mirrors the form: it stored st.session_state['_user_email']
    # in requests.user_email and falls back to submitted_by_email.
    creator_email = r["user_email"] or r["submitted_by_email"]

    return {
        "case_id": r["case_id"],
        "payload": payload,
        "creator_email": creator_email,
        "submitted_by_email": r["submitted_by_email"],
    }


def retry_pending_notifications(
    session: Session,
    *,
    min_id: Optional[int] = None,
    limit: int = 50,
) -> dict[str, int]:
    """Re-attempt delivery for mailer-era requests left un-notified.

    Selects ``requests`` with ``email_notified_at IS NULL`` and ``id >=``
    cutoff (the mailer-era boundary, or ``min_id`` if given), then calls
    ``send_request_notification`` for each. The send is idempotent, so this is
    safe to run on every app load and/or from a scheduled job.

    Returns a tally ``{"attempted", "sent", "skipped", "failed"}``.
    """
    from services.mailer import send_request_notification

    tally = {"attempted": 0, "sent": 0, "skipped": 0, "failed": 0}

    cutoff = min_id if min_id is not None else _mailer_era_min_id(session)
    if cutoff is None:
        # Nothing has ever been notified -> no mailer era -> nothing to redeliver
        # (and we must never touch the legacy pre-mailer rows).
        return tally

    rows = session.execute(
        text(
            """
            SELECT id FROM requests
             WHERE email_notified_at IS NULL
               AND id >= :cutoff
             ORDER BY id DESC
             LIMIT :limit
            """
        ),
        {"cutoff": cutoff, "limit": limit},
    ).fetchall()

    for (request_id,) in rows:
        tally["attempted"] += 1
        try:
            built = build_payload_from_request(session, request_id)
            if not built:
                tally["skipped"] += 1
                continue
            sent = send_request_notification(
                session=session,
                case_id=built["case_id"],
                payload=built["payload"],
                creator_email=built["creator_email"],
                submitted_by_email=built["submitted_by_email"],
            )
            if sent:
                tally["sent"] += 1
            else:
                tally["skipped"] += 1
        except MailerError as e:
            tally["failed"] += 1
            logger.warning(
                "retry_pending_notifications: send failed for request",
                extra={"request_id": request_id, "error": str(e)},
            )
        except Exception:  # noqa: BLE001 - one bad row must not abort the sweep
            tally["failed"] += 1
            logger.exception(
                "retry_pending_notifications: unexpected error",
                extra={"request_id": request_id},
            )

    logger.info("retry_pending_notifications: done", extra=tally)
    return tally
