from typing import Optional
from datetime import datetime

import streamlit as st
from database.db import SessionLocal
from database.crud.documents import (
    get_internal_status,
    get_shipping_lines_status,
    get_ports_status,
    get_customs_status,
    get_comments_by_request,
    get_comment_entries,
    get_razon_social_by_request,
    get_requests_for_progress,
    get_audit_timeline,
    get_last_status_change_time,
)
from utils.form_helpers import cached_profiles_list, cached_profile_id, status_id_to_name_map
from utils.ui_helpers import status_badge
from utils.timezone import to_colombia_tz
from config.constants import DEFAULT_PAGE_SIZE


def _sla_badge(last_change: Optional[datetime]) -> str:
    """Return an HTML badge indicating time in current status."""
    if not last_change:
        return ""
    delta = datetime.utcnow() - last_change
    days = delta.days
    if days < 3:
        color = "#10b981"  # green
    elif days < 7:
        color = "#f59e0b"  # amber
    else:
        color = "#ef4444"  # red

    label = f"{days}d" if days > 0 else "hoy"
    return f' <span style="background:{color};color:white;padding:1px 6px;border-radius:8px;font-size:11px;">{label}</span>'

# ==========================
#   VISTA DE PROGRESO
# ==========================

def show_progress_view(current_user_email: Optional[str] = None, is_admin: bool = False):
    st.subheader("Visualizacion del Progreso de Solicitudes")

    session = SessionLocal()

    try:
        email_filter = None if is_admin else (current_user_email or None)

        # --- Quick search (C2) ---
        search_term = st.text_input(
            "Buscar por empresa, ID o email",
            placeholder="Escribe para filtrar...",
            key="progress_search",
        )

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

        # Apply search filter
        if search_term:
            term = search_term.lower().strip()
            requests = [
                r for r in requests
                if term in (r.get("company_name") or "").lower()
                or term in str(r.get("id", ""))
                or term in (r.get("user_email") or "").lower()
            ]
            total_count = len(requests)

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
                with st.expander("Lineas Navieras", expanded=True):
                    for line in lines:
                        sname = status_map.get(line.status_id, "Sin estado")
                        sla = _sla_badge(get_last_status_change_time(session, "shipping_line_registration", line.id))
                        st.markdown(f"- {line.line_name}: {status_badge(sname)}{sla}", unsafe_allow_html=True)

            ports = get_ports_status(session, request_id)
            if ports:
                with st.expander("Puertos y Terminales", expanded=True):
                    grouped_ports = {}
                    for p in ports:
                        grouped_ports.setdefault(p.port_name, []).append(p)

                    for port, terminals in grouped_ports.items():
                        st.write(f"**{port}**")
                        for term in terminals:
                            terminal_label = f" ({term.terminal_name})" if term.terminal_name else ""
                            sname = status_map.get(term.status_id, "Sin estado")
                            sla = _sla_badge(get_last_status_change_time(session, "port_registration", term.id))
                            st.markdown(f" - Terminal{terminal_label}: {status_badge(sname)}{sla}", unsafe_allow_html=True)

            customs = get_customs_status(session, request_id)
            if customs:
                with st.expander("Aduanas", expanded=True):
                    for c in customs:
                        sname = status_map.get(c.status_id, "Sin estado")
                        sla = _sla_badge(get_last_status_change_time(session, "customs_registration", c.id))
                        st.markdown(f"- {c.customs_name}: {status_badge(sname)}{sla}", unsafe_allow_html=True)

            # === Progress bar (A3) ===
            total_items = 0
            approved_items = 0
            approved_status_id = None
            # status_map is {id: name} from status_id_to_name_map()
            for s_id, s_name in status_map.items():
                if isinstance(s_name, str) and "aprobado" in s_name.lower():
                    approved_status_id = s_id
                    break

            if lines:
                total_items += len(lines)
                approved_items += sum(1 for ln in lines if ln.status_id == approved_status_id)
            if ports:
                total_items += len(ports)
                approved_items += sum(1 for p in ports if p.status_id == approved_status_id)
            if customs:
                total_items += len(customs)
                approved_items += sum(1 for c in customs if c.status_id == approved_status_id)
            if internal_status_id == approved_status_id:
                approved_items += 1
            total_items += 1  # internal always counts

            if total_items > 0:
                pct = approved_items / total_items
                st.markdown(f"**Progreso general:** {approved_items}/{total_items} aprobados")
                st.progress(pct)

            # === Threaded comments (B1) ===
            comment_entries = get_comment_entries(session, request_id)
            with st.expander("Comentarios y Seguimiento", expanded=bool(comment_entries)):
                if comment_entries:
                    for entry in comment_entries:
                        created = entry["created_at"]
                        date_str = (
                            to_colombia_tz(created).strftime("%Y-%m-%d %H:%M")
                            if created else "sin fecha"
                        )
                        author = entry["author_name"] or entry["author_email"]
                        entry_type = entry["entry_type"]
                        type_tag = {"rechazo": " [RECHAZO]", "nota": " [NOTA]"}.get(entry_type, "")

                        st.markdown(f"**{author}**{type_tag} - _{date_str}_")
                        st.markdown(f"> {entry['content']}")

                        if entry.get("image_drive_link"):
                            st.markdown(f"[{entry.get('image_file_name', 'imagen')}]({entry['image_drive_link']})")

                        st.markdown("---")
                else:
                    # Fall back to legacy comments
                    comments_data = get_comments_by_request(session, request_id)
                    if comments_data:
                        st.write("**Comentarios:**")
                        st.write(f"{comments_data['comments'] or '—'}")
                        st.write("**Seguimiento / Notificaciones:**")
                        st.write(f"{comments_data['notifications'] or '—'}")
                    else:
                        st.caption("Sin comentarios registrados.")

            # === Activity timeline (A1) ===
            timeline = get_audit_timeline(session, request_id)
            if timeline:
                with st.expander("Historial de actividad", expanded=False):
                    for event in timeline:
                        ts = event["timestamp"]
                        ts_str = (
                            to_colombia_tz(ts).strftime("%Y-%m-%d %H:%M")
                            if ts else "—"
                        )
                        action_icons = {
                            "CREATE": "🆕",
                            "UPLOAD": "📎",
                            "STATUS_CHANGE": "🔄",
                            "UPDATE": "✏️",
                        }
                        icon = action_icons.get(event["action"], "•")
                        user = event["user_email"].split("@")[0] if event["user_email"] else "—"
                        detail = event["details"] or event["action"]

                        st.markdown(f"{icon} **{ts_str}** - {user} - {detail}")

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
