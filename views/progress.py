"""Progreso — view page."""
import streamlit as st
from forms.view_progress import show_progress_view

st.markdown('<div class="page-title">Progreso de Solicitudes</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Seguimiento del estado de todas las solicitudes</div>', unsafe_allow_html=True)

user_email = st.session_state.get("_user_email")
is_admin = st.session_state.get("_is_admin", False)

show_progress_view(current_user_email=user_email, is_admin=is_admin)
