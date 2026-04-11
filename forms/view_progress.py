from typing import Optional

import streamlit as st
from database.db import SessionLocal
from database.crud.documents import (
    get_internal_status,
    get_shipping_lines_status,
    get_ports_status,
    get_customs_status,
    get_comments_by_request,
    get_razon_social_by_request,
    get_requests_for_progress,
)
from utils.form_helpers import cached_profiles_list, cached_profile_id, status_id_to_name_map
from utils.ui_helpers import status_badge
from config.constants import DEFAULT_PAGE_SIZE

# ==========================
#   VISTA DE PROGRESO
# ==========================

def show_progress_view(current_user_email: Optional[str] = None, is_admin: bool = False):
    st.subheader("📊 Visualización del Progreso de Solicitudes")

    session = SessionLocal()

    try:
        email_filter = None if is_admin else (current_user_email or None)

        page_key = "progress_page"
        if page_key not in st.session_state:
            st.session_state[page_key] = 0

        requests, total_count = get_requests_for_progress(
            session,
            only_for_email=email_filter,
            page=st.session_state[page_key],
            page_size=DEFAULT_PAGE_SIZE,
        )
        if not requests:
            st.info("No hay solicitudes para mostrar.")
            return

        companies = sorted({r.get("company_name") for r in requests if r.get("company_name")})

        all_profile_names = cached_profiles_list() or []
        name_to_id = {}
        for name in all_profile_names:
            pid = cached_profile_id(name)
            if pid:
                name_to_id[name] = pid

        present_profile_ids = {r.get("profile_id") for r in requests if r.get("profile_id") is not None}
        available_profiles = [(name, pid) for name, pid in name_to_id.items() if pid in present_profile_ids]
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
        
        profile_id = cached_profile_id(profile_name)
        filtered_requests = [
            r for r in requests
            if r.get("company_name") == company_name and r.get("profile_id") == profile_id
        ]

        if not filtered_requests:
            st.warning("No hay solicitudes registradas para esta combinación.")
            return

        status_map = status_id_to_name_map()

        for r in filtered_requests:
            request_id = r["id"]

            st.markdown(f"---\n### Solicitud {company_name}")

            registro = get_razon_social_by_request(session, request_id)

            colA, colB = st.columns(2)
            if registro:
                with colA:
                    st.write(f"**Razón Social:** {registro.get('razon_social') or '—'}")
                with colB:
                    fecha_creacion = registro.get("fecha_creacion")
                    if fecha_creacion:
                        st.write(f"**Fecha de Creación:** {fecha_creacion.strftime('%Y-%m-%d')}")
                    else:
                        st.write("**Fecha de Creación:** —")
            else:
                with colA:
                    st.write("**Razón Social:** —")
                with colB:
                    st.write("**Fecha de Creación:** —")

            internal_status_id = get_internal_status(session, request_id)
            internal_status = status_map.get(internal_status_id, "Sin estado")
            st.markdown(f"**Registro Interno:** {status_badge(internal_status)}", unsafe_allow_html=True)

            lines = get_shipping_lines_status(session, request_id)
            if lines:
                with st.expander("🚢 Líneas Navieras", expanded=True):
                    for line in lines:
                        sname = status_map.get(line.status_id, "Sin estado")
                    st.markdown(f"- {line.line_name}: {status_badge(sname)}", unsafe_allow_html=True)

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
                            sname = status_map.get(term.status_id, "Sin estado")
                            st.markdown(f" - Terminal{terminal_label}: {status_badge(sname)}", unsafe_allow_html=True)

            # === Aduanas
            customs = get_customs_status(session, request_id)
            if customs:
                with st.expander("🧾 Aduanas", expanded=True):
                    for c in customs:
                        sname = status_map.get(c.status_id, "Sin estado")
                    st.markdown(f"- {c.customs_name}: {status_badge(sname)}", unsafe_allow_html=True)

            comments_data = get_comments_by_request(session, request_id)
            st.markdown("#### 🗒️ Comentarios y Seguimiento")
            if comments_data:
                st.write("**Comentarios:**")
                st.write(f"{comments_data['comments'] or '—'}")
                st.write("**Seguimiento / Notificaciones:**")
                st.write(f"{comments_data['notifications'] or '—'}")
            else:
                st.caption("Sin comentarios registrados para esta solicitud.")

        # --- Pagination controls ---
        total_pages = max(1, (total_count + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE)
        col_prev, col_info, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("< Anterior", disabled=st.session_state[page_key] == 0):
                st.session_state[page_key] -= 1
                st.rerun()
        with col_info:
            st.caption(f"Pagina {st.session_state[page_key] + 1} de {total_pages} ({total_count} solicitudes)")
        with col_next:
            if st.button("Siguiente >", disabled=st.session_state[page_key] >= total_pages - 1):
                st.session_state[page_key] += 1
                st.rerun()

    finally:
        session.close()
