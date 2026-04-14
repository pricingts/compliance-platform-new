"""CRUD for the users table.

All reads/writes against `users` go through this module. The admin panel in
forms/admin_users_form.py is the primary consumer.

Emails are stored lowercase and compared case-insensitively.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "email": row[0],
        "nombre_display": row[1],
        "rol": row[2],
        "activo": bool(row[3]),
        "created_at": row[4] if len(row) > 4 else None,
        "created_by": row[5] if len(row) > 5 else None,
    }


def insert_user(
    session: Session,
    email: str,
    nombre_display: str,
    rol: str,
    activo: bool = True,
    created_by: Optional[str] = None,
) -> None:
    """Insert a new user. Raises if email already exists."""
    session.execute(
        text("""
            INSERT INTO users (email, nombre_display, rol, activo, created_by)
            VALUES (:email, :nombre_display, :rol, :activo, :created_by)
        """),
        {
            "email": email.lower().strip(),
            "nombre_display": nombre_display,
            "rol": rol,
            "activo": bool(activo),
            "created_by": created_by,
        },
    )
    session.commit()


def update_user(
    session: Session,
    email: str,
    *,
    nombre_display: Optional[str] = None,
    rol: Optional[str] = None,
    activo: Optional[bool] = None,
) -> None:
    """Partial update: only the fields you pass get changed."""
    updates: list[str] = []
    params: dict[str, Any] = {"email": email.lower().strip()}
    if nombre_display is not None:
        updates.append("nombre_display = :nombre_display")
        params["nombre_display"] = nombre_display
    if rol is not None:
        updates.append("rol = :rol")
        params["rol"] = rol
    if activo is not None:
        updates.append("activo = :activo")
        params["activo"] = bool(activo)
    if not updates:
        return
    sql = f"UPDATE users SET {', '.join(updates)} WHERE LOWER(email) = :email"
    session.execute(text(sql), params)
    session.commit()


def set_user_inactive(session: Session, email: str) -> None:
    """Soft-delete: marks activo=FALSE but keeps the row."""
    update_user(session, email, activo=False)


def get_user_by_email(session: Session, email: str) -> Optional[dict[str, Any]]:
    """Return a dict with user fields, or None if not found. Case-insensitive."""
    if not email:
        return None
    row = session.execute(
        text("""
            SELECT email, nombre_display, rol, activo, created_at, created_by
              FROM users
             WHERE LOWER(email) = :email
        """),
        {"email": email.lower().strip()},
    ).fetchone()
    return _row_to_dict(row) if row else None


def list_users(
    session: Session,
    filter_rol: Optional[str] = None,
    activo_only: bool = True,
) -> list[dict[str, Any]]:
    """List users, optionally filtered by rol and/or activo.

    Default `activo_only=True` excludes deactivated users.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if filter_rol is not None:
        clauses.append("rol = :rol")
        params["rol"] = filter_rol
    if activo_only:
        clauses.append("activo = 1")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT email, nombre_display, rol, activo, created_at, created_by
          FROM users
          {where}
         ORDER BY nombre_display ASC
    """
    rows = session.execute(text(sql), params).fetchall()
    return [_row_to_dict(r) for r in rows]
