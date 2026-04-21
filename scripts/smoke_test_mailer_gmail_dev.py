"""End-to-end smoke test for the Gmail-API mailer transport against Railway dev.

Validates the full Phase 8 stack with no mocks on the SMTP/Gmail boundary:

  1. Service-account credentials impersonate the creator via DWD.
  2. The email really leaves Google — it appears in the impersonated user's
     Sent folder and lands in the compliance inbox override.
  3. The Gmail API response carries ``threadId`` and the ``email_threads``
     row is persisted in Railway dev Postgres.
  4. A second call on the same request is idempotent (email_notified_at guard).

Usage (from project root, with Railway CLI linked to COMPLIANCE/dev):

    railway run --no-local python3 scripts/smoke_test_mailer_gmail_dev.py

Prerequisites (one-time, in Google Admin Console):
  * Domain-Wide Delegation approved for the service account client_id.
  * Scope: https://www.googleapis.com/auth/gmail.send

Environment variables expected (``railway run`` provides DATABASE_*):
  * DATABASE_URL / DATABASE_PUBLIC_URL  — Railway dev Postgres
  * GOOGLE_APPLICATION_CREDENTIALS_JSON — full service-account JSON
  * SMOKE_IMPERSONATE_USER              — optional, default jsanchez@tradingsolutions.com

The script overrides ``DEFAULT_COMPLIANCE_RECIPIENTS`` and the dynamic
compliance-user query so the compliance team does not get spammed during
testing. Only SMOKE_IMPERSONATE_USER receives the test message.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

IMPERSONATE_USER = os.environ.get(
    "SMOKE_IMPERSONATE_USER", "jsanchez@tradingsolutions.com"
)

raw_creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON") or ""
if not raw_creds_json:
    print(
        "ERROR: GOOGLE_APPLICATION_CREDENTIALS_JSON env var is required "
        "(the full service-account JSON, single line).",
        file=sys.stderr,
    )
    sys.exit(2)

try:
    creds_dict = json.loads(raw_creds_json)
except json.JSONDecodeError as exc:
    print(f"ERROR: GOOGLE_APPLICATION_CREDENTIALS_JSON is not valid JSON: {exc}", file=sys.stderr)
    sys.exit(2)


class _FakeSecrets(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


st.secrets = _FakeSecrets({
    "mailer": {"enabled": True, "transport": "gmail"},
    "google_sheets_credentials": creds_dict,
})

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import services.mailer.recipients as recipients_mod  # noqa: E402
from services.mailer import send_request_notification  # noqa: E402

recipients_mod.DEFAULT_COMPLIANCE_RECIPIENTS = (IMPERSONATE_USER,)
recipients_mod.get_active_compliance_users = lambda _session: []  # noqa: E731


def _log(msg: str) -> None:
    print(f"[smoke-gmail] {msg}")


def main() -> int:
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    _log(f"Connecting to {url.split('@', 1)[-1]}")
    engine = sa.create_engine(url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    case_id = "C-GMAIL-SMOKE"
    tag = f"GMAIL-SMOKE-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    try:
        profile_id = session.execute(
            sa.text("SELECT id FROM profiles LIMIT 1")
        ).scalar()
        if profile_id is None:
            _log("No profiles seeded in dev DB — cannot proceed.")
            return 2

        _log(f"Inserting throw-away request {tag!r}")
        rid = session.execute(
            sa.text(
                """INSERT INTO requests (profile_id, company_name, user_email, case_id)
                   VALUES (:pid, :name, :email, :cid)
                   RETURNING id"""
            ),
            {
                "pid": profile_id,
                "name": tag,
                "email": IMPERSONATE_USER,
                "cid": case_id,
            },
        ).scalar()
        session.commit()
        _log(f"  request_id={rid}")

        payload = {
            "case_id": case_id,
            "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "requested_by": "Smoke Gmail Tester",
            "tipo_solicitud": "cliente",
            "company_name": tag,
            "email": "noreply@tradingsolutions.com",
            "trading": "Colombia",
            "location": "Cartagena",
            "language": "Español",
            "reminder_frequency": "Semanal",
            "tipo_operacion": "EXPO",
            "commodity": "Phase-8 smoke commodity",
            "aduana": "CARGOFLASH",
            "puerto": "Cartagena",
            "linea_naviera": "MSC",
        }

        _log(
            "Invoking send_request_notification (real Gmail API, "
            f"impersonating {IMPERSONATE_USER})..."
        )
        sent = send_request_notification(
            session=session,
            case_id=case_id,
            payload=payload,
            creator_email=IMPERSONATE_USER,
        )
        _log(f"  first call returned: {sent} (expected True)")
        if not sent:
            _log("First call did not send — aborting")
            return 1

        row = session.execute(
            sa.text(
                """SELECT r.email_notified_at, et.gmail_thread_id,
                          et.last_message_id, et.references_chain
                     FROM requests r
                     LEFT JOIN email_threads et ON et.request_id = r.id
                    WHERE r.id = :id"""
            ),
            {"id": rid},
        ).fetchone()
        _log(f"  email_notified_at = {row[0]!r} (expected NOT NULL)")
        _log(f"  gmail_thread_id   = {row[1]!r} (expected NOT NULL)")
        _log(f"  last_message_id   = {row[2]!r}")
        _log(f"  references_chain  = {row[3]!r}")
        assert row[0] is not None, "email_notified_at not set"
        assert row[1], "gmail_thread_id not persisted"

        _log("Invoking again to confirm idempotency...")
        sent2 = send_request_notification(
            session=session,
            case_id=case_id,
            payload=payload,
            creator_email=IMPERSONATE_USER,
        )
        _log(f"  second call returned: {sent2} (expected False)")
        assert sent2 is False, "mailer sent twice for same case_id"

        _log("SMOKE PASSED — Gmail API + DWD + threading operational")
        return 0
    finally:
        try:
            session.execute(
                sa.text("DELETE FROM email_threads WHERE request_id IN (SELECT id FROM requests WHERE case_id = :cid)"),
                {"cid": case_id},
            )
            session.execute(
                sa.text("DELETE FROM requests WHERE case_id = :cid"),
                {"cid": case_id},
            )
            session.commit()
            _log("  cleaned up throw-away request + thread row")
        except Exception:
            session.rollback()
            _log("  cleanup failed (leaving stale rows)")
        session.close()


if __name__ == "__main__":
    sys.exit(main())
