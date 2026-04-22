"""End-to-end smoke test for the compliance mailer against Railway dev.

Runs everything for real EXCEPT the recipient list, which is overridden to
jsanchez@tradingsolutions.com so the compliance team isn't spammed during
testing. All other layers (DB round-trip, SMTP handshake, HTML rendering,
idempotency) are exercised end-to-end.

Usage (from project root, with Railway CLI linked to COMPLIANCE/dev):
    railway run --no-local python3 scripts/smoke_test_mailer_dev.py

Requires these env vars (provided automatically by ``railway run``):
    DATABASE_URL / DATABASE_PUBLIC_URL  - Railway dev Postgres
Requires these extra env vars (seeded by this script at runtime):
    SMTP_*                              - credentials passed by the operator

The script:
  1. Seeds fake ``st.secrets`` so the mailer's feature flag turns on.
  2. Patches the recipient list to [jsanchez@tradingsolutions.com].
  3. Creates a throw-away request in Railway dev Postgres.
  4. Invokes send_request_notification() which performs a REAL SMTP send.
  5. Verifies the DB row's ``email_notified_at`` is set.
  6. Re-invokes to confirm idempotency (no second mail).
  7. Deletes the throw-away request.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# --- 0. ensure project root importable ------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- 1. fake st.secrets BEFORE the app imports happen ---------------------
import streamlit as st  # noqa: E402

SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD") or ""
if not SMTP_PASSWORD:
    print("ERROR: set SMTP_PASSWORD before running this script", file=sys.stderr)
    sys.exit(2)


class _FakeSecrets(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


st.secrets = _FakeSecrets({
    "mailer": {"enabled": True},
    "smtp": {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "use_tls": os.environ.get("SMTP_USE_TLS", "false").lower() in ("1", "true", "yes"),
        "username": os.environ.get("SMTP_USERNAME", "compliance@tradingsolutions.com"),
        "password": SMTP_PASSWORD,
        "from_addr": os.environ.get("SMTP_FROM_ADDR", "compliance@tradingsolutions.com"),
    },
})

# --- 2. imports that read secrets ----------------------------------------
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import services.mailer.recipients as recipients_mod  # noqa: E402
from services.mailer import send_request_notification  # noqa: E402

# Override recipients: only jsanchez during smoke test.
recipients_mod.DEFAULT_COMPLIANCE_RECIPIENTS = (
    "jsanchez@tradingsolutions.com",
)
# Also bypass the dynamic query (we don't want compliance users from DB).
recipients_mod.get_active_compliance_users = lambda _session: []  # noqa: E731


def _log(msg: str) -> None:
    print(f"[smoke] {msg}")


def main() -> int:
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    _log(f"Connecting to {url.split('@', 1)[-1]}")
    engine = sa.create_engine(url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    tag = f"SMOKE-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    case_id = "C-SMOKE"

    try:
        # Fetch an existing profile_id to satisfy FK.
        profile_id = session.execute(
            sa.text("SELECT id FROM profiles LIMIT 1")
        ).scalar()
        if profile_id is None:
            _log("No profiles seeded in dev DB — cannot proceed.")
            return 2

        # --- 3. insert throw-away request --------------------------------
        _log(f"Inserting throw-away request {tag!r}")
        rid = session.execute(
            sa.text("""
                INSERT INTO requests (profile_id, company_name, user_email, case_id)
                VALUES (:pid, :name, :email, :cid)
                RETURNING id
            """),
            {
                "pid": profile_id,
                "name": tag,
                "email": "jsanchez@tradingsolutions.com",
                "cid": case_id,
            },
        ).scalar()
        session.commit()
        _log(f"  request_id={rid}")

        # --- 4. real SMTP send -------------------------------------------
        payload = {
            "case_id": case_id,
            "fecha": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "requested_by": "Smoke Tester",
            "tipo_solicitud": "cliente",
            "company_name": tag,
            "email": "noreply@tradingsolutions.com",
            "trading": "Colombia",
            "location": "Cartagena",
            "language": "Español",
            "reminder_frequency": "Semanal",
            "tipo_operacion": "EXPO",
            "commodity": "Smoke-test commodity",
            "aduana": "CARGOFLASH",
            "puerto": "Cartagena",
            "linea_naviera": "MSC",
        }
        _log("Invoking send_request_notification (real SMTP to jsanchez@)...")
        sent = send_request_notification(
            session=session,
            case_id=case_id,
            payload=payload,
            creator_email="jsanchez@tradingsolutions.com",
        )
        _log(f"  first call returned: {sent} (expected True)")
        if not sent:
            _log("First call did not send — aborting")
            return 1

        # --- 5. verify email_notified_at --------------------------------
        ts = session.execute(
            sa.text("SELECT email_notified_at FROM requests WHERE id = :id"),
            {"id": rid},
        ).scalar()
        _log(f"  email_notified_at = {ts!r} (expected NOT NULL)")
        assert ts is not None, "email_notified_at not set"

        # --- 6. idempotency --------------------------------------------
        _log("Invoking again to confirm idempotency...")
        sent2 = send_request_notification(
            session=session,
            case_id=case_id,
            payload=payload,
            creator_email="jsanchez@tradingsolutions.com",
        )
        _log(f"  second call returned: {sent2} (expected False)")
        assert sent2 is False, "mailer sent twice for same case_id"

        _log("SMOKE PASSED")
        return 0
    finally:
        # --- 7. cleanup throw-away request -------------------------------
        try:
            session.execute(
                sa.text("DELETE FROM requests WHERE case_id = :cid"),
                {"cid": case_id},
            )
            session.commit()
            _log("  cleaned up throw-away request")
        except Exception:
            session.rollback()
            _log("  cleanup failed (leaving stale row)")
        session.close()


if __name__ == "__main__":
    sys.exit(main())
