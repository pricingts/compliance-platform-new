import streamlit as st


def check_authentication():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        if not st.user.is_logged_in:
            st.warning("Por favor, inicia sesion primero.")
            if st.button("Log in"):
                st.login()
            st.stop()
        else:
            st.session_state.authenticated = True

    if not st.user.is_logged_in:
        st.session_state.authenticated = False
        st.stop()
