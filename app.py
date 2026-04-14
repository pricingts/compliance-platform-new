"""Compliance Platform — main entry point with st.navigation()."""
from typing import Optional

import streamlit as st
from services.authentication import check_authentication
from utils.ui_helpers import load_css, render_sidebar_user
from database.db import SessionLocal
from database.crud.documents import get_unread_notifications, mark_notifications_read
from services.users import resolve_role, get_user

st.set_page_config(page_title="Compliance Platform", layout="wide")
load_css()


def identity_role(email: Optional[str]) -> str:
    """Return the effective role for the given email.

    Source of truth is the `users` table. Unknown or inactive users get 'otro'.
    The super-admin (jsanchez@tradingsolutions.com) is seeded into the table;
    every other user is managed via the admin panel in the UI.
    """
    if not email:
        return "otro"
    session = SessionLocal()
    try:
        return resolve_role(session, email)
    finally:
        session.close()


def _load_user_display_name(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    session = SessionLocal()
    try:
        user = get_user(session, email)
        return user["nombre_display"] if user else None
    finally:
        session.close()


# --- Authentication ---
check_authentication()

# If we reach here, user is authenticated
_st_user = getattr(st, "user", None)
user_email = getattr(_st_user, "email", None) if _st_user else None
user_name = getattr(_st_user, "name", "Usuario") if _st_user else "Developer"

# Local dev fallback: use env var or default admin email
if user_email is None:
    import os
    user_email = os.environ.get("DEV_USER_EMAIL", "jsanchez@tradingsolutions.com")

role = identity_role(user_email)
is_admin = (role == "compliance")

# Prefer nombre_display from users table if available
_display_name = _load_user_display_name(user_email)
if _display_name:
    user_name = _display_name

# Store user context in session_state for views to access
st.session_state["_user_email"] = user_email
st.session_state["_user_role"] = role
st.session_state["_user_display_name"] = user_name
st.session_state["_is_admin"] = is_admin

# Phase 7: dispatch due reminders, gated to once every 5 minutes per session
# to avoid hammering the DB on every Streamlit rerun.
from datetime import datetime as _dt, timedelta as _td

_last_run_key = "_reminders_last_run"
_last_run = st.session_state.get(_last_run_key)
if _last_run is None or (_dt.utcnow() - _last_run) > _td(minutes=5):
    try:
        from services.reminders import process_due_reminders
        _rem_session = SessionLocal()
        try:
            process_due_reminders(_rem_session, current_user_email=user_email)
        finally:
            _rem_session.close()
        st.session_state[_last_run_key] = _dt.utcnow()
    except Exception:
        # Never block login on reminder failures
        pass

# --- Navigation (only rendered when authenticated) ---
pages_compliance = [
    st.Page("views/dashboard.py", title="Dashboard", icon=":material/dashboard:"),
    st.Page("views/request.py", title="Solicitud de Creacion", icon=":material/edit_note:"),
    st.Page("views/upload_documents.py", title="Registro de Documentos", icon=":material/upload_file:"),
    st.Page("views/progress.py", title="Progreso", icon=":material/monitoring:"),
    st.Page("views/admin_users.py", title="Admin Usuarios", icon=":material/admin_panel_settings:"),
]

pages_other = [
    st.Page("views/my_requests.py", title="Mis Solicitudes", icon=":material/list_alt:"),
    st.Page("views/request.py", title="Solicitud de Creacion", icon=":material/edit_note:"),
    st.Page("views/progress.py", title="Progreso", icon=":material/monitoring:"),
]

pages = pages_compliance if is_admin else pages_other

# --- Brand above nav (st.logo is the only way to render above st.navigation) ---
st.logo("assets/brand_sidebar.svg", icon_image="assets/brand_sidebar_small.svg")

pg = st.navigation(pages)

# --- Sidebar: notifications + user info ---
with st.sidebar:
    # Notifications badge (A2)
    _notif_session = None
    try:
        _notif_session = SessionLocal()
        notifications = get_unread_notifications(_notif_session, user_email or "")
        if notifications:
            with st.expander(f"Notificaciones ({len(notifications)})", expanded=False):
                for n in notifications[:10]:
                    st.markdown(f"- {n['message']}")
                if st.button("Marcar como leidas", key="mark_read"):
                    mark_notifications_read(_notif_session, user_email or "")
                    _notif_session.commit()
                    _notif_session.close()
                    _notif_session = None
                    st.rerun()
    except Exception:
        pass
    finally:
        if _notif_session is not None:
            _notif_session.close()

    render_sidebar_user(user_name or "", user_email or "")
    if hasattr(st, "logout"):
        if st.button("Cerrar sesion", use_container_width=True):
            st.logout()
            st.session_state.authenticated = False
            st.rerun()

pg.run()
