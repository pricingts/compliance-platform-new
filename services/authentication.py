import streamlit as st

# st.user requires Streamlit >= 1.55 (Streamlit Cloud OAuth).
# For local development, we auto-authenticate as a dev user.
_has_st_user = hasattr(st, "user") and hasattr(getattr(st, "user", None), "is_logged_in")


def check_authentication():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not _has_st_user:
        # Local dev mode — auto-authenticate
        st.session_state.authenticated = True
        return

    if not st.session_state.authenticated:
        if not st.user.is_logged_in:
            # Hide sidebar on login screen
            st.markdown(
                "<style>[data-testid='stSidebar']{display:none}</style>",
                unsafe_allow_html=True,
            )
            st.warning("Por favor, inicia sesion primero.")
            if st.button("Log in"):
                st.login()
            st.stop()
        else:
            st.session_state.authenticated = True

    if not st.user.is_logged_in:
        st.session_state.authenticated = False
        st.stop()
