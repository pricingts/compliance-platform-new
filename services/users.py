"""User & role resolution service.

This module is the single source of truth for "what role does this email have?"
Callers: app.py (identity_role), forms/request_form.py (role-aware rendering),
forms/admin_users_form.py (management), views/my_requests.py (filtering).

Resolution precedence:
1. Look up email in the `users` table. If found AND activo=TRUE → return that rol.
2. Otherwise → 'otro'.

Notes:
- There is intentionally no fallback to ADMIN_EMAILS config. The super-admin
  must be seeded into the users table (migrations/seed_super_admin.sql).
- All lookups are case-insensitive on email.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from database.crud.users import get_user_by_email, list_users
from database.crud.inside_sales_assignments import get_assignments_for_is


VALID_ROLES = ("comercial", "inside_sales", "compliance", "otro")
DEFAULT_ROLE = "otro"


def get_user(session: Session, email: Optional[str]) -> Optional[dict[str, Any]]:
    """Fetch a user dict by email. Case-insensitive. Returns None if missing."""
    return get_user_by_email(session, email) if email else None


def resolve_role(session: Session, email: Optional[str]) -> str:
    """Return the effective role for an email.

    - Unknown email → 'otro'
    - User with activo=FALSE → 'otro'
    - Otherwise → whatever `rol` is stored on the user row
    """
    user = get_user(session, email)
    if user is None:
        return DEFAULT_ROLE
    if not user["activo"]:
        return DEFAULT_ROLE
    rol = user["rol"]
    return rol if rol in VALID_ROLES else DEFAULT_ROLE


def is_comercial(session: Session, email: Optional[str]) -> bool:
    return resolve_role(session, email) == "comercial"


def is_inside_sales(session: Session, email: Optional[str]) -> bool:
    return resolve_role(session, email) == "inside_sales"


def is_compliance(session: Session, email: Optional[str]) -> bool:
    return resolve_role(session, email) == "compliance"


def get_active_comerciales(session: Session) -> list[dict[str, Any]]:
    """List all active comerciales, sorted by nombre_display."""
    return list_users(session, filter_rol="comercial", activo_only=True)


def get_active_compliance_users(session: Session) -> list[dict[str, Any]]:
    """Return active users with rol='compliance'.

    Used by the mailer to dynamically discover compliance staff who should
    receive new-request notifications in addition to the hardcoded compliance
    shared mailboxes.
    """
    return list_users(session, filter_rol="compliance", activo_only=True)


def get_comerciales_for_inside_sales(
    session: Session, inside_sales_email: Optional[str],
) -> list[dict[str, Any]]:
    """List comerciales assigned to an IS — filtered to only the active ones.

    An IS can only create requests for comerciales that are:
    - Still assigned to them
    - Still active in the users table

    If the IS email is None/unknown or has no assignments, returns [].
    """
    if not inside_sales_email:
        return []
    assignments = get_assignments_for_is(session, inside_sales_email)
    if not assignments:
        return []
    assigned_emails = {a["comercial_email"].lower() for a in assignments}
    # Filter to only active comerciales still in users table
    active = get_active_comerciales(session)
    return [c for c in active if c["email"].lower() in assigned_emails]
