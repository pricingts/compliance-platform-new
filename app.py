"""Compliance Platform — main entry point with st.navigation()."""
from typing import Optional

import streamlit as st
from services.authentication import check_authentication
from config.settings import get_admin_emails
from utils.ui_helpers import load_css, render_sidebar_brand, render_sidebar_user

st.set_page_config(page_title="Compliance Platform", layout="wide")
load_css()


def identity_role(email: Optional[str]) -> str:
    if not email:
        return "other"
    allowed_emails = get_admin_emails()
    return "compliance" if email.lower() in allowed_emails else "other"


# --- Authentication ---
check_authentication()

user_email = getattr(getattr(st, "user", None), "email", None)
user_name = getattr(getattr(st, "user", None), "name", "Usuario")

role = identity_role(user_email)
is_admin = (role == "compliance")

# Store user context in session_state for views to access
st.session_state["_user_email"] = user_email
st.session_state["_is_admin"] = is_admin

# --- Navigation ---
pages_compliance = [
    st.Page("views/request.py", title="Solicitud de Creacion", icon=":material/edit_note:"),
    st.Page("views/upload_documents.py", title="Registro de Documentos", icon=":material/upload_file:"),
    st.Page("views/progress.py", title="Progreso", icon=":material/monitoring:"),
]

pages_other = [
    st.Page("views/request.py", title="Solicitud de Creacion", icon=":material/edit_note:"),
    st.Page("views/progress.py", title="Progreso", icon=":material/monitoring:"),
]

pages = pages_compliance if is_admin else pages_other

# --- Sidebar ---
with st.sidebar:
    render_sidebar_brand()
    st.markdown("---")

pg = st.navigation(pages)

with st.sidebar:
    st.markdown("---")
    render_sidebar_user(user_email or "")
    if st.button("Cerrar sesion", use_container_width=True):
        st.logout()
        st.session_state.authenticated = False
        st.rerun()

pg.run()
