"""One-off backfill for compliance creation-notifications that never went out.

Background: 12 mailer-era requests (ids >= the first-notified id) were saved
with ``email_notified_at IS NULL`` and never produced a notification email —
each was confirmed ABSENT from the compliance mailbox before this script was
written. This resends them. The send is idempotent (``send_request_notification``
skips any row already marked notified), so re-running is safe.

SAFE BY DEFAULT: without ``--send`` the script only LISTS what it would do.

It must run where the mailer's Gmail service-account credentials and config
exist (Streamlit Cloud, or any host with the env below). It does NOT run from a
laptop that lacks those secrets.

    # dry-run (no emails sent) — lists the candidates:
    DATABASE_URL=... python scripts/backfill_notifications.py

    # actually resend (real emails to compliance):
    DATABASE_URL=... \
    GOOGLE_APPLICATION_CREDENTIALS_JSON='{...service account json...}' \
    MAILER_ENABLED=true MAILER_TRANSPORT=gmail \
    python scripts/backfill_notifications.py --send

Flags:
    --send              Actually send (default is dry-run / list only).
    --all               Consider every mailer-era un-notified row, not just the
                        verified allow-list below.
    --case-ids C..,C..  Explicit comma-separated case_id list (overrides default).
    --db-url URL        DB URL (else DATABASE_URL / DATABASE_PUBLIC_URL env).
"""
from __future__ import annotations

import argparse
import os
import sys

# Make the repo root importable when run as `python scripts/backfill_notifications.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import bindparam, create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.logging_config import get_logger  # noqa: E402

logger = get_logger(__name__)

# The 12 active-era failures whose notification was confirmed ABSENT from the
# compliance mailbox (subject "Solicitud de Registro - <case>") on 2026-06-17.
VERIFIED_MISSING = [
    "C0080", "C0087", "C0096", "C0098", "C0100", "C0101",
    "C0105", "C0109", "C0112", "C0114", "C0119", "C0121",
]


def _make_session(db_url: str | None):
    url = db_url or os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if not url:
        raise SystemExit(
            "No DB URL. Pass --db-url or set DATABASE_URL / DATABASE_PUBLIC_URL."
        )
    engine = create_engine(url)
    return sessionmaker(bind=engine)()


def _candidates(session, *, use_all: bool, case_ids: list[str]):
    from services.mailer.pending import _mailer_era_min_id

    cutoff = _mailer_era_min_id(session)
    if cutoff is None:
        return []  # nothing ever notified -> no mailer era -> nothing to do
    if use_all:
        rows = session.execute(
            text(
                "SELECT id, case_id, company_name, email FROM requests "
                "WHERE email_notified_at IS NULL AND id >= :c ORDER BY id"
            ),
            {"c": cutoff},
        ).fetchall()
    else:
        rows = session.execute(
            text(
                "SELECT id, case_id, company_name, email FROM requests "
                "WHERE email_notified_at IS NULL AND case_id IN :ids ORDER BY id"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": case_ids},
        ).fetchall()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missed compliance notifications.")
    parser.add_argument("--send", action="store_true", help="Actually send (default: dry-run).")
    parser.add_argument("--all", action="store_true", help="All mailer-era un-notified rows.")
    parser.add_argument("--case-ids", default="", help="Comma-separated case_id allow-list.")
    parser.add_argument("--db-url", default=None)
    args = parser.parse_args()

    case_ids = (
        [c.strip() for c in args.case_ids.split(",") if c.strip()]
        if args.case_ids
        else VERIFIED_MISSING
    )

    session = _make_session(args.db_url)
    try:
        rows = _candidates(session, use_all=args.all, case_ids=case_ids)
        print(f"Mailer-era un-notified candidates: {len(rows)}")
        for r in rows:
            print(f"  id={r[0]:>4}  {r[1]:<7}  {(r[2] or '')[:30]:<30}  {r[3] or ''}")

        if not args.send:
            print("\nDRY-RUN — no emails sent. Re-run with --send (and Gmail creds) to deliver.")
            return 0

        from services.mailer import send_request_notification, validate_mailer_config
        from services.mailer.pending import build_payload_from_request

        cfg = validate_mailer_config()
        if not cfg["enabled"]:
            raise SystemExit(
                "Mailer is DISABLED (set MAILER_ENABLED=true or st.secrets) — refusing to send."
            )
        if not cfg["ok"]:
            raise SystemExit(f"Mailer config problems, refusing to send: {cfg['problems']}")

        sent = skipped = failed = 0
        for r in rows:
            rid, case_id = r[0], r[1]
            try:
                built = build_payload_from_request(session, rid)
                if not built:
                    skipped += 1
                    continue
                ok = send_request_notification(
                    session=session,
                    case_id=built["case_id"],
                    payload=built["payload"],
                    creator_email=built["creator_email"],
                    submitted_by_email=built["submitted_by_email"],
                )
                if ok:
                    sent += 1
                    print(f"  SENT   {case_id}")
                else:
                    skipped += 1
                    print(f"  SKIP   {case_id} (already notified / no recipients)")
            except Exception as e:  # noqa: BLE001 - keep going; report at end
                failed += 1
                print(f"  FAIL   {case_id}: {type(e).__name__}: {e}")
                logger.exception("Backfill send failed for %s", case_id)

        print(f"\nDone. sent={sent} skipped={skipped} failed={failed}")
        return 0 if failed == 0 else 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
