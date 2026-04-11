"""Dashboard — compliance overview page."""
import streamlit as st
from forms.dashboard_view import show_dashboard

st.markdown('<div class="page-title">Dashboard de Compliance</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Vision general del estado de solicitudes y registros</div>', unsafe_allow_html=True)

show_dashboard()
