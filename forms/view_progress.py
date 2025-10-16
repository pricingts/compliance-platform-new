import streamlit as st
import pandas as pd
from datetime import datetime
from database.db import SessionLocal
from database.crud.documents import (
    get_all_company_names,
    get_profiles_list,
    get_profile_id_by_name,
    get_requests_by_company_and_profile,
    get_internal_status,
    get_shipping_lines_status,
    get_ports_status,
    get_customs_status,
    get_all_statuses,
    get_comments_by_request,
    get_razon_social_by_request,
    get_requests_for_progress
)

# ==========================
#   VISTA DE PROGRESO
# ==========================

def show_progress_view(current_user_email: str | None = None, is_admin: bool = False):
    st.set_page_config(page_title="📊 Progreso de Solicitudes", layout="wide")
    st.subheader("📊 Visualización del Progreso de Solicitudes")

    session = SessionLocal()

    try:
        email_filter = None if is_admin else (current_user_email or None)
        requests = get_requests_for_progress(session, only_for_email=email_filter)
        if not requests:
            st.info("No hay solicitudes para mostrar.")
            return
        
        companies = sorted({r.get("company_name") for r in requests if r.get("company_name")})

        all_profile_names = get_profiles_list(session) or []  # p.ej. ["Cliente", "Proveedor", ...]
        name_to_id = {}
        for name in all_profile_names:
            pid = get_profile_id_by_name(session, name)
            if pid:
                name_to_id[name] = pid

        # Perfiles realmente presentes en las solicitudes filtradas (disponibles para selección)
        present_profile_ids = {r.get("profile_id") for r in requests if r.get("profile_id") is not None}
        available_profiles = [(name, pid) for name, pid in name_to_id.items() if pid in present_profile_ids]
        # Orden alfabético por nombre
        available_profiles.sort(key=lambda x: x[0])

        col1, col2 = st.columns(2)

        with col1:
            company_name = st.selectbox(
                "Empresa",
                companies,
                index=None,
                placeholder="Selecciona una compañía..."
            )

        with col2:
            profile_name = st.selectbox(
                "Perfil",
                [name for (name, _) in available_profiles],
                index=None,
                placeholder="Selecciona un perfil..."
            )

        if not company_name or not profile_name:
            st.info("Selecciona una compañía y un perfil para ver el progreso.")
            return

        profile_id = get_profile_id_by_name(session, profile_name)
        requests = get_requests_by_company_and_profile(session, company_name, profile_id)

        if not requests:
            st.warning("No hay solicitudes registradas para esta combinación.")
            return

        status_map = {v: k for k, v in get_all_statuses(session).items()} 
        for r in requests:
            request_id = r["id"]
            fecha = r.get("created_at")
            fecha_str = fecha.strftime("%Y-%m-%d") if isinstance(fecha, datetime) else "Sin fecha"

            st.markdown(f"---\n### Solicitud {company_name}")

            colA, colB = st.columns(2)
            with colA:
                razon_social = get_razon_social_by_request(session, request_id)
                st.write(f"**Razón Social:** {razon_social or '—'}")
            with colB:
                st.write(f"**Fecha de Creación:** {fecha_str}")

            internal_status_id = get_internal_status(session, request_id)
            internal_status = status_map.get(internal_status_id, "Sin estado")
            st.write(f"**Registro Interno:** {internal_status}")

            lines = get_shipping_lines_status(session, request_id)
            if lines:
                with st.expander("🚢 Líneas Navieras", expanded=True):
                    for l in lines:
                        st.write(f"- {l.line_name}: **{status_map.get(l.status_id, 'Sin estado')}**")
            else:
                st.caption("Sin líneas navieras registradas.")

            ports = get_ports_status(session, request_id)
            if ports:
                with st.expander("⚓ Puertos y Terminales", expanded=True):
                    grouped_ports = {}
                    for p in ports:
                        grouped_ports.setdefault(p.port_name, []).append(p)

                    for port, terminals in grouped_ports.items():
                        st.write(f"**{port}**")
                        for term in terminals:
                            terminal_label = f" ({term.terminal_name})" if term.terminal_name else ""
                            st.write(f" - Terminal{terminal_label}: **{status_map.get(term.status_id, 'Sin estado')}**")
            else:
                st.caption("Sin puertos registrados.")

            # === Aduanas
            customs = get_customs_status(session, request_id)
            if customs:
                with st.expander("🧾 Aduanas", expanded=True):
                    for c in customs:
                        st.write(f"- {c.customs_name}: **{status_map.get(c.status_id, 'Sin estado')}**")
            else:
                st.caption("Sin aduanas registradas.")

        comments_data = get_comments_by_request(session, request_id)
        st.markdown("#### 🗒️ Comentarios y Seguimiento")
        if comments_data:
            st.write(f"**Comentarios:**")
            st.write(f"{comments_data['comments'] or '—'}")
            st.write(f"**Seguimiento / Notificaciones:**")
            st.write(f"{comments_data['notifications'] or '—'}")
        else:
            st.caption("Sin comentarios registrados para esta solicitud.")

    finally:
        session.close()
