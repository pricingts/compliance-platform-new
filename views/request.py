import streamlit as st
from forms.request_form import forms

def show():
    st.subheader("📝 Solicitud de Creación de Asociado de Negocio")
    forms()

