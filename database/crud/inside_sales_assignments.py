"""CRUD for the inside_sales_comerciales many-to-many link table.

An Inside Sales user can support several comerciales. The form of solicitud
shows only the comerciales assigned to the current IS (not the full list).
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def assign_comercial(
    session: Session,
    inside_sales_email: str,
    comercial_email: str,
    assigned_by: Optional[str] = None,
) -> None:
    """Create an assignment. Idempotent: ignores duplicates (composite PK)."""
    # SQLite and Postgres both support INSERT ... ON CONFLICT DO NOTHING.
    session.execute(
        text("""
            INSERT INTO inside_sales_comerciales
                (inside_sales_email, comercial_email, assigned_by)
            VALUES (:is_email, :c_email, :by)
            ON CONFLICT (inside_sales_email, comercial_email) DO NOTHING
        """),
        {
            "is_email": inside_sales_email.lower().strip(),
            "c_email": comercial_email.lower().strip(),
            "by": assigned_by,
        },
    )
    session.commit()


def remove_assignment(
    session: Session,
    inside_sales_email: str,
    comercial_email: str,
) -> None:
    session.execute(
        text("""
            DELETE FROM inside_sales_comerciales
             WHERE LOWER(inside_sales_email) = :is_email
               AND LOWER(comercial_email) = :c_email
        """),
        {
            "is_email": inside_sales_email.lower().strip(),
            "c_email": comercial_email.lower().strip(),
        },
    )
    session.commit()


def get_assignments_for_is(
    session: Session, inside_sales_email: str,
) -> list[dict[str, Any]]:
    """Return list of {comercial_email, assigned_at, assigned_by} for the IS."""
    rows = session.execute(
        text("""
            SELECT comercial_email, assigned_at, assigned_by
              FROM inside_sales_comerciales
             WHERE LOWER(inside_sales_email) = :is_email
             ORDER BY comercial_email
        """),
        {"is_email": inside_sales_email.lower().strip()},
    ).fetchall()
    return [
        {"comercial_email": r[0], "assigned_at": r[1], "assigned_by": r[2]}
        for r in rows
    ]


def get_inside_sales_for_comercial(
    session: Session, comercial_email: str,
) -> list[dict[str, Any]]:
    """Inverse: list of IS assigned to a given comercial."""
    rows = session.execute(
        text("""
            SELECT inside_sales_email, assigned_at, assigned_by
              FROM inside_sales_comerciales
             WHERE LOWER(comercial_email) = :c_email
             ORDER BY inside_sales_email
        """),
        {"c_email": comercial_email.lower().strip()},
    ).fetchall()
    return [
        {"inside_sales_email": r[0], "assigned_at": r[1], "assigned_by": r[2]}
        for r in rows
    ]
