import streamlit as st

def check_authentication():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        if not st.user.is_logged_in:
            st.warning("Por favor, inicia sesión primero.")
            if st.button("Log in ➡️"):
                st.login()
            st.stop()
        else:
            st.header(f"Hello, {st.user.name}!")
            st.session_state.authenticated = True

    if st.user.is_logged_in:
        col1, col2, col3 = st.columns([1, 1.55, 0.3])
        with col3:
            if st.button("Log out"):
                st.logout()
                st.session_state.authenticated = False
                st.rerun() 
    else:
        st.session_state.authenticated = False
        st.stop()