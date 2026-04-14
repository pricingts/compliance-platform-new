"""Streamlit page wrapper for 'Mis Solicitudes' (Phase 6 / F6).

Visible only to non-compliance roles. Compliance has its own global
dashboard at views/dashboard.py.
"""
import streamlit as st

from database.db import SessionLocal
from forms.my_requests_view import render_my_requests


_session = SessionLocal()
try:
    _email = st.session_state.get("_user_email") or ""
    render_my_requests(_session, _email)
finally:
    _session.close()
