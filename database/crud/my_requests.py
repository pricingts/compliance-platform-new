"""Personal-dashboard queries for the 'Mis Solicitudes' page (Phase 6 / F6).

Used by `views/my_requests.py` to list each non-compliance user's own
requests, including those they submitted on behalf of a comercial
(Inside Sales scenario).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_my_requests(
    session: Session, user_email: str, limit: int = 100,
) -> list[dict[str, Any]]:
    """Return requests where the user is the owner OR the submitter (IS).

    Sorted newest-first by created_at.
    """
    if not user_email:
        return []
    rows = session.execute(text("""
        SELECT r.id, r.case_id, r.company_name, r.created_at,
               r.user_email, r.submitted_by_email, r.commercial,
               p.name AS profile_name
          FROM requests r
          LEFT JOIN profiles p ON p.id = r.profile_id
         WHERE LOWER(r.user_email) = :email
            OR LOWER(COALESCE(r.submitted_by_email, '')) = :email
         ORDER BY r.created_at DESC, r.id DESC
         LIMIT :limit
    """), {"email": user_email.lower().strip(), "limit": limit}).fetchall()
    return [
        {
            "id": r[0],
            "case_id": r[1] or f"C{r[0]:04d}",
            "company_name": r[2],
            "created_at": r[3],
            "user_email": r[4],
            "submitted_by_email": r[5],
            "commercial": r[6],
            "profile_name": r[7],
        }
        for r in rows
    ]


def aggregate_status(statuses: list[str | None]) -> str:
    """Reduce a list of registration statuses to a single global status.

    Priority order:
    1. Any 'rechazado' → 'Con rechazos'
    2. Any 'en revision' → 'En revisión'
    3. All non-empty and all 'aprobado' → 'Completa'
    4. Otherwise → 'Pendiente'
    """
    cleaned = [s for s in statuses if s]
    if not cleaned:
        return "Pendiente"
    if any(s == "rechazado" for s in cleaned):
        return "Con rechazos"
    if any(s == "en revision" for s in cleaned):
        return "En revisión"
    if all(s == "aprobado" for s in cleaned):
        return "Completa"
    return "Pendiente"


def get_aggregated_status_for_request(session: Session, request_id: int) -> str:
    """Compute the global status for one request by joining all 4 registration tables."""
    rows = session.execute(text("""
        SELECT s.status FROM customs_registration t LEFT JOIN status s ON s.id=t.status_id WHERE t.request_id=:rid
        UNION ALL
        SELECT s.status FROM port_registration t LEFT JOIN status s ON s.id=t.status_id WHERE t.request_id=:rid
        UNION ALL
        SELECT s.status FROM shipping_line_registration t LEFT JOIN status s ON s.id=t.status_id WHERE t.request_id=:rid
        UNION ALL
        SELECT s.status FROM internal_registration t LEFT JOIN status s ON s.id=t.status_id WHERE t.request_id=:rid
    """), {"rid": request_id}).fetchall()
    return aggregate_status([r[0] for r in rows])
