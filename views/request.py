"""Solicitud de Creacion — view page."""
import streamlit as st
from forms.request_form import forms

st.markdown('<div class="page-title">Solicitud de Creacion</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Crear nueva solicitud de cliente o proveedor</div>', unsafe_allow_html=True)

forms()
