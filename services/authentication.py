import streamlit as st


def check_authentication():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    # st.user is only available on Streamlit Community Cloud with auth enabled
    user = getattr(st, "user", None)

    if not st.session_state.authenticated:
        if user is None or not getattr(user, "is_logged_in", False):
            st.warning("Por favor, inicia sesion primero.")
            if st.button("Log in"):
                st.login()
            st.stop()
        else:
            st.header(f"Hello, {user.name}!")
            st.session_state.authenticated = True

    if user is not None and getattr(user, "is_logged_in", False):
        col1, col2, col3 = st.columns([1, 1.55, 0.3])
        with col3:
            if st.button("Log out"):
                st.logout()
                st.session_state.authenticated = False
                st.rerun()
    else:
        st.session_state.authenticated = False
        st.stop()
