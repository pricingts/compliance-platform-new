import streamlit as st
from services.authentication import check_authentication

st.set_page_config(page_title="Compliance Platform", layout="wide")


# --- Roles ---
def identity_role(email: str | None) -> str:

    if not email:
        return "other"

    usernames = {"compliance", "compliance1", "compliance2", "sjaafar"}
    domains = {"@tradingsolutions.com", "@tradingsol.com"}

    allowed_emails = {u + d for u in usernames for d in domains}
    return "compliance" if email.lower() in allowed_emails else "other"


col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("images/logo_trading.png")

check_authentication()

user_email = getattr(getattr(st, "user", None), "email", None)
user_name = getattr(getattr(st, "user", None), "name", "Usuario")

role = identity_role(user_email)
is_admin = (role == "compliance")

# Páginas visibles por rol
pages_by_role: dict[str, list[str]] = {
    "compliance": ["Home", "Solicitud de Creación", "Registro de Proveedores/ Clientes", "Progreso"],
    "other":      ["Home", "Solicitud de Creación", "Progreso"],
}

allowed_pages = pages_by_role.get(role, pages_by_role["other"])

with st.sidebar:
    page = st.radio("Go to", allowed_pages, index=0)

if page == "Solicitud de Creación":
    import views.request as req
    req.show()

elif page == "Registro de Proveedores/ Clientes":
    import views.upload_documents as up
    up.show()

# elif page == "Progreso":
#     import views.visualization as nt
#     nt.show(current_user_email=user_email, is_admin=is_admin)