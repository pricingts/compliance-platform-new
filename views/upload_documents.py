"""Registro de Documentos — view page."""
import streamlit as st
from forms.upload_documents_form import forms

st.markdown('<div class="page-title">Registro de Documentos</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Cargar documentos y actualizar estados</div>', unsafe_allow_html=True)

forms()
