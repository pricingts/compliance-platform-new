"""CRUD for email_threads — persistence for Gmail threading.

Stores, per request, the Gmail threadId plus the running Message-ID chain so
subsequent emails (reminders, status changes) thread into the same Gmail
conversation as the original creation email.

Created by migration 007.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_thread_by_request_id(
    session: Session, request_id: int
) -> Optional[dict]:
    """Return the thread row for a request as a dict, or None if missing."""
    row = session.execute(
        text(
            """
            SELECT id, request_id, gmail_thread_id, last_message_id,
                   references_chain, created_at, updated_at
              FROM email_threads
             WHERE request_id = :rid
            """
        ),
        {"rid": request_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "request_id": row[1],
        "gmail_thread_id": row[2],
        "last_message_id": row[3],
        "references_chain": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


def upsert_thread(
    session: Session,
    request_id: int,
    gmail_thread_id: Optional[str],
    last_message_id: str,
    references_chain: Optional[str] = None,
) -> None:
    """Insert or update the thread for a request.

    When the thread already existed, the *previous* ``last_message_id`` is
    appended to ``references_chain`` so the chain grows monotonically across
    events (creation -> reminder -> reminder -> ...). Passing ``None`` for
    ``gmail_thread_id`` preserves the existing value via COALESCE.
    """
    existing = get_thread_by_request_id(session, request_id)
    dialect = session.bind.dialect.name if session.bind else "unknown"
    now_clause = "NOW()" if dialect == "postgresql" else "CURRENT_TIMESTAMP"

    if existing is None:
        session.execute(
            text(
                f"""
                INSERT INTO email_threads
                    (request_id, gmail_thread_id, last_message_id, references_chain,
                     created_at, updated_at)
                VALUES
                    (:rid, :tid, :mid, :ref, {now_clause}, {now_clause})
                """
            ),
            {
                "rid": request_id,
                "tid": gmail_thread_id,
                "mid": last_message_id,
                "ref": references_chain or "",
            },
        )
    else:
        # Append the previously-stored last_message_id to the references chain
        # so every event adds one ID to the chain. Space-separated, matching
        # the RFC 5322 References header convention.
        chain = (existing["references_chain"] or "").strip()
        prev_mid = existing["last_message_id"] or ""
        new_chain = (chain + " " + prev_mid).strip() if prev_mid else chain
        session.execute(
            text(
                f"""
                UPDATE email_threads
                   SET gmail_thread_id = COALESCE(:tid, gmail_thread_id),
                       last_message_id = :mid,
                       references_chain = :ref,
                       updated_at = {now_clause}
                 WHERE request_id = :rid
                """
            ),
            {
                "rid": request_id,
                "tid": gmail_thread_id,
                "mid": last_message_id,
                "ref": new_chain,
            },
        )
    session.commit()
