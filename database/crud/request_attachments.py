"""CRUD for request_attachments — files uploaded as part of the initial request.

These are distinct from `registration` (which holds compliance-required
documents like RUT, certifications). Attachments are free-form supporting
files the requester adds when creating the solicitud.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_request_attachment(
    session: Session,
    request_id: int,
    file_name: str,
    drive_link: str,
    uploaded_by: str,
) -> Optional[int]:
    """Insert an attachment row and return its id.

    Mirrors the dual-dialect pattern used in clientes.insert_client_request:
    Postgres uses RETURNING, SQLite uses last_insert_rowid().
    """
    dialect = session.bind.dialect.name if session.bind else "unknown"
    params = {
        "request_id": request_id,
        "file_name": file_name,
        "drive_link": drive_link,
        "uploaded_by": uploaded_by,
    }
    if dialect == "postgresql":
        att_id = session.execute(
            text("""
                INSERT INTO request_attachments (request_id, file_name, drive_link, uploaded_by)
                VALUES (:request_id, :file_name, :drive_link, :uploaded_by)
                RETURNING id
            """),
            params,
        ).scalar()
    else:
        session.execute(
            text("""
                INSERT INTO request_attachments (request_id, file_name, drive_link, uploaded_by)
                VALUES (:request_id, :file_name, :drive_link, :uploaded_by)
            """),
            params,
        )
        att_id = session.execute(
            text("SELECT id FROM request_attachments WHERE rowid = last_insert_rowid()")
        ).scalar()
    session.commit()
    return att_id


def get_request_attachments(session: Session, request_id: int) -> list[dict[str, Any]]:
    """Return all attachments for a request, oldest first."""
    rows = session.execute(
        text("""
            SELECT id, request_id, file_name, drive_link, uploaded_by, uploaded_at
              FROM request_attachments
             WHERE request_id = :rid
             ORDER BY uploaded_at ASC, id ASC
        """),
        {"rid": request_id},
    ).fetchall()
    return [
        {
            "id": r[0],
            "request_id": r[1],
            "file_name": r[2],
            "drive_link": r[3],
            "uploaded_by": r[4],
            "uploaded_at": r[5],
        }
        for r in rows
    ]
