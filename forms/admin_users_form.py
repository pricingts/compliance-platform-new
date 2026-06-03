"""Admin Users Panel — CRUD for users and inside-sales assignments.

The UI is split into three tabs:
- Lista: browse / edit / deactivate users
- Nuevo Usuario: create a new user
- Asignaciones: assign comerciales to inside-sales

Heavy logic lives in small pure helpers (`_validate_new_user_data`,
`_can_deactivate`) so they can be unit-tested without Streamlit.
"""
from __future__ import annotations

from typing import Iterable

import streamlit as st

from config.constants import ALLOWED_EMAIL_DOMAINS
from database.crud.inside_sales_assignments import (
    assign_comercial,
    get_assignments_for_is,
    remove_assignment,
)
from database.crud.users import (
    create_user_if_absent,
    list_users,
    set_user_inactive,
    update_user,
)
from services.audit import log_action
from services.users import VALID_ROLES
from utils.validators import sanitize_text

# Must stay in sync with migrations/seed_super_admin.sql
SUPER_ADMIN_EMAIL = "jsanchez@tradingsolutions.com"


# ---------------------------------------------------------------------------
# Pure helpers (testable without Streamlit)
# ---------------------------------------------------------------------------


def _validate_new_user_data(
    email: str | None,
    nombre_display: str | None,
    rol: str | None,
    allowed_domains: Iterable[str],
) -> tuple[bool, str]:
    """Validate data for a new user row.

    Returns (is_valid, error_message). `error_message` is empty when valid.
    """
    if not email or not isinstance(email, str) or not email.strip():
        return False, "El email es obligatorio."
    if "@" not in email:
        return False, "El email no tiene un formato valido."
    # Reuse is_allowed_email_domain for domain enforcement (single source of truth)
    allowed_set = {d.lower() for d in allowed_domains}
    domain = email.strip().rsplit("@", 1)[1].lower()
    if not domain or domain not in allowed_set:
        return False, (
            "El dominio del email no esta permitido. "
            f"Dominios validos: {', '.join(sorted(allowed_set))}."
        )
    if not nombre_display or not isinstance(nombre_display, str) or not nombre_display.strip():
        return False, "El nombre para mostrar es obligatorio."
    if not rol or rol not in VALID_ROLES:
        return False, (
            f"El rol debe ser uno de: {', '.join(VALID_ROLES)}."
        )
    return True, ""


def _can_deactivate(email: str | None, super_admin_email: str) -> bool:
    """Return False if `email` matches the super-admin (case-insensitive).

    Defensive: None/empty never matches super-admin, so returns True.
    """
    if not email or not isinstance(email, str):
        return True
    return email.strip().lower() != super_admin_email.strip().lower()


# ---------------------------------------------------------------------------
# Streamlit UI — thin wrappers around CRUD + audit logging
# ---------------------------------------------------------------------------


def _current_admin_email() -> str:
    """Return the email of the admin currently using the panel."""
    return st.session_state.get("_user_email") or "unknown"


def _render_lista_tab(session) -> None:
    st.subheader("Usuarios existentes")
    show_inactive = st.checkbox("Mostrar inactivos", value=False, key="admin_users_show_inactive")
    users = list_users(session, activo_only=not show_inactive)
    if not users:
        st.info("No hay usuarios registrados todavia.")
        return

    for user in users:
        email = user["email"]
        with st.expander(f"{user['nombre_display']}  —  {email}  ({user['rol']})", expanded=False):
            col1, col2 = st.columns(2)
            new_nombre = col1.text_input(
                "Nombre",
                value=user["nombre_display"],
                key=f"edit_nombre_{email}",
            )
            new_rol = col2.selectbox(
                "Rol",
                options=list(VALID_ROLES),
                index=list(VALID_ROLES).index(user["rol"]) if user["rol"] in VALID_ROLES else 0,
                key=f"edit_rol_{email}",
            )
            if st.button("Guardar cambios", key=f"save_{email}"):
                old_snapshot = {"nombre_display": user["nombre_display"], "rol": user["rol"]}
                update_user(session, email, nombre_display=new_nombre, rol=new_rol)
                log_action(
                    session,
                    user_email=_current_admin_email(),
                    action="UPDATE",
                    entity_type="user",
                    entity_id=None,
                    old_value=old_snapshot,
                    new_value={"nombre_display": new_nombre, "rol": new_rol},
                    details=f"email={email}",
                )
                session.commit()
                st.success("Usuario actualizado.")
                st.rerun()

            if user["activo"]:
                can_deactivate = _can_deactivate(email, SUPER_ADMIN_EMAIL)
                if not can_deactivate:
                    st.caption("El super-admin no puede desactivarse desde la UI.")
                if st.button(
                    "Desactivar",
                    key=f"deactivate_{email}",
                    disabled=not can_deactivate,
                ):
                    set_user_inactive(session, email)
                    log_action(
                        session,
                        user_email=_current_admin_email(),
                        action="UPDATE",
                        entity_type="user",
                        entity_id=None,
                        old_value={"activo": True},
                        new_value={"activo": False},
                        details=f"email={email}",
                    )
                    session.commit()
                    st.success("Usuario desactivado.")
                    st.rerun()
            else:
                if st.button("Reactivar", key=f"reactivate_{email}"):
                    update_user(session, email, activo=True)
                    log_action(
                        session,
                        user_email=_current_admin_email(),
                        action="UPDATE",
                        entity_type="user",
                        entity_id=None,
                        old_value={"activo": False},
                        new_value={"activo": True},
                        details=f"email={email}",
                    )
                    session.commit()
                    st.success("Usuario reactivado.")
                    st.rerun()


def _render_nuevo_usuario_tab(session) -> None:
    st.subheader("Crear nuevo usuario")
    with st.form("admin_users_new_form"):
        email = st.text_input("Email", key="new_user_email")
        nombre_display = st.text_input("Nombre para mostrar", key="new_user_nombre")
        rol = st.selectbox("Rol", options=list(VALID_ROLES), key="new_user_rol")
        submitted = st.form_submit_button("Crear usuario")

    if not submitted:
        return

    email_clean = sanitize_text(email or "").lower()
    nombre_clean = sanitize_text(nombre_display or "")
    is_valid, err = _validate_new_user_data(
        email_clean, nombre_clean, rol, ALLOWED_EMAIL_DOMAINS,
    )
    if not is_valid:
        st.error(err)
        return

    admin_email = _current_admin_email()
    # Race-safe create: returns False (instead of raising IntegrityError) if the
    # email already exists, even under a concurrent create by another admin.
    if not create_user_if_absent(
        session,
        email=email_clean,
        nombre_display=nombre_clean,
        rol=rol,
        created_by=admin_email,
    ):
        st.error("Ya existe un usuario con ese email.")
        return

    log_action(
        session,
        user_email=admin_email,
        action="CREATE",
        entity_type="user",
        entity_id=None,
        new_value={"email": email_clean, "nombre_display": nombre_clean, "rol": rol},
        details=f"email={email_clean}",
    )
    session.commit()
    st.success(f"Usuario {email_clean} creado.")


def _render_asignaciones_tab(session) -> None:
    st.subheader("Asignaciones Inside Sales -> Comerciales")
    inside_sales = list_users(session, filter_rol="inside_sales", activo_only=True)
    comerciales = list_users(session, filter_rol="comercial", activo_only=True)

    if not inside_sales:
        st.info("No hay usuarios inside_sales activos.")
        return
    if not comerciales:
        st.info("No hay comerciales activos.")
        return

    is_options = {f"{u['nombre_display']} ({u['email']})": u["email"] for u in inside_sales}
    c_options = {f"{u['nombre_display']} ({u['email']})": u["email"] for u in comerciales}

    selected_is_label = st.selectbox(
        "Inside Sales",
        options=list(is_options.keys()),
        key="assign_is_select",
    )
    selected_is_email = is_options[selected_is_label]

    current = get_assignments_for_is(session, selected_is_email)
    current_emails = {a["comercial_email"].lower() for a in current}

    st.markdown("**Comerciales asignados**")
    if not current:
        st.caption("Ninguno todavia.")
    for a in current:
        col1, col2 = st.columns([4, 1])
        col1.write(a["comercial_email"])
        if col2.button("Quitar", key=f"rm_{selected_is_email}_{a['comercial_email']}"):
            remove_assignment(session, selected_is_email, a["comercial_email"])
            log_action(
                session,
                user_email=_current_admin_email(),
                action="DELETE",
                entity_type="inside_sales_assignment",
                entity_id=None,
                old_value={
                    "inside_sales_email": selected_is_email,
                    "comercial_email": a["comercial_email"],
                },
                details=f"is={selected_is_email} comercial={a['comercial_email']}",
            )
            session.commit()
            st.rerun()

    available = {label: em for label, em in c_options.items() if em.lower() not in current_emails}
    if not available:
        st.caption("Todos los comerciales ya estan asignados a este IS.")
        return

    new_c_label = st.selectbox(
        "Agregar comercial",
        options=list(available.keys()),
        key="assign_new_c_select",
    )
    if st.button("Asignar", key="assign_new_c_btn"):
        new_c_email = available[new_c_label]
        admin_email = _current_admin_email()
        assign_comercial(session, selected_is_email, new_c_email, assigned_by=admin_email)
        log_action(
            session,
            user_email=admin_email,
            action="CREATE",
            entity_type="inside_sales_assignment",
            entity_id=None,
            new_value={
                "inside_sales_email": selected_is_email,
                "comercial_email": new_c_email,
            },
            details=f"is={selected_is_email} comercial={new_c_email}",
        )
        session.commit()
        st.success("Asignacion creada.")
        st.rerun()


def render_admin_users_panel(session) -> None:
    """Main entry point — renders the admin Users panel with 3 tabs."""
    st.markdown('<div class="page-title">Administracion de Usuarios</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Crear, editar y asignar usuarios del sistema</div>',
        unsafe_allow_html=True,
    )
    tab_lista, tab_nuevo, tab_asign = st.tabs(["Lista", "Nuevo Usuario", "Asignaciones"])
    with tab_lista:
        _render_lista_tab(session)
    with tab_nuevo:
        _render_nuevo_usuario_tab(session)
    with tab_asign:
        _render_asignaciones_tab(session)
