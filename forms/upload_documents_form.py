# form_documents_existing.py

import os
import unicodedata
import streamlit as st
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from sqlalchemy import text
from database.db import SessionLocal
from database.crud.documents import *

# Google Drive utils
from services.google_drive_utils import init_drive, find_or_create_folder, upload_to_drive

CO_TZ = ZoneInfo("America/Bogota")

# ==========================
# 🔧 FUNCIONES AUXILIARES
# ==========================

def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()


def is_security_verification(doc_name: str) -> bool:
    return "verificaciones de seguridad" in _slug(doc_name)


def _to_colombia_tz(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CO_TZ)


def sanitize_filename(name: str) -> str:
    return name.replace(",", " - ").replace("/", "_").replace("\\", "_").strip()


def render_status_controls(session, request_id):
    """Renderiza los selectbox de estado para cada bloque y retorna el mapa de status."""
    st.markdown("### ⚙️ Estado de registros por bloque")

    status_map = get_all_statuses(session)
    status_labels = list(status_map.keys())

    # === Documentos internos (global)
    st.markdown("#### 📁 Documentos internos")
    st.selectbox(
        "Estado documentos internos",
        status_labels,
        key=f"status_internal_{request_id}"
    )

    # === Líneas navieras
    lines = get_shipping_lines_status(session, request_id)
    if lines:
        st.markdown("#### 🚢 Líneas navieras")
        for line in lines:
            st.selectbox(
                f"{line.line_name}",
                status_labels,
                index=(line.status_id - 1) if line.status_id else 1,
                key=f"line_status_{line.id}"
            )

    # === Puertos y terminales
    ports = get_ports_status(session, request_id)
    if ports:
        st.markdown("#### ⚓ Puertos y terminales")
        grouped = {}
        for p in ports:
            grouped.setdefault(p.port_name, []).append(p)
        for port, terminals in grouped.items():
            st.markdown(f"**{port}**")
            for term in terminals:
                name = term.terminal_name or "(sin terminal)"
                st.selectbox(
                    f"{name}",
                    status_labels,
                    index=(term.status_id - 1) if term.status_id else 1,
                    key=f"port_status_{term.id}"
                )

    # === Aduanas
    customs = get_customs_status(session, request_id)
    if customs:
        st.markdown("#### 🧾 Aduanas")
        for c in customs:
            st.selectbox(
                f"{c.customs_name}",
                status_labels,
                index=(c.status_id - 1) if c.status_id else 1,
                key=f"customs_status_{c.id}"
            )

    return status_map

def forms():
    st.subheader("📎 Carga de documentos")

    session = SessionLocal()

    try:
        # ====================================
        # 🔹 SELECCIÓN DE COMPAÑÍA Y PERFIL
        # ====================================
        companies = get_all_company_names(session)
        profiles = get_profiles_list(session)

        col1, col2 = st.columns(2)
        with col1:
            company_name = st.selectbox(
                "Nombre de la compañía",
                companies,
                index=None if companies else None,
                placeholder="Selecciona la compañía..."
            )
        with col2:
            profile_name = st.selectbox(
                "Perfil",
                profiles,
                index=None if profiles else None,
                placeholder="Selecciona el perfil..."
            )

        if not company_name or not profile_name:
            st.info("Selecciona una compañía y un perfil para continuar.")
            return

        profile_id = get_profile_id_by_name(session, profile_name)
        if not profile_id:
            st.error("❌ El perfil seleccionado no existe.")
            return

        # ====================================
        # 🔹 SELECCIÓN DE SOLICITUD
        # ====================================
        requests = get_requests_by_company_and_profile(session, company_name, profile_id)
        if not requests:
            st.warning("No hay solicitudes para esta compañía y perfil.")
            return

        options = [f"ID {r['id']}" for r in requests]
        idx = 0
        if len(options) > 1:
            idx = st.selectbox(
                "Selecciona la solicitud",
                list(range(len(options))),
                format_func=lambda i: options[i],
                index=None,
                placeholder="Selecciona una solicitud..."
            )
            if idx is None:
                st.info("Selecciona una solicitud para continuar.")
                return

        selected_request = requests[idx if len(options) > 1 else 0]
        request_id = selected_request["id"]

        # ====================================
        # 🔹 DATOS BASE
        # ====================================
        col1, col2 = st.columns(2)
        with col1:
            razon_social = st.text_input("Razón Social", key=f"razon_social_{request_id}")
        with col2:
            fecha_creacion = st.date_input("Fecha de Creación", key=f"fecha_creacion_{request_id}")

        status_map = get_all_statuses(session)
        status_labels = list(status_map.keys())
        uploaded_buffers = {}

        # ====================================
        # 🗂️ BLOQUE REGISTRO INTERNO
        # ====================================
        st.markdown("### Registro interno")

        internal_docs = {
            "Documentos de la empresa": "empresa",
            "Documentos de vinculación": "vinculacion",
            "Verificación de seguridad": "seguridad"
        }

        for label, key_suffix in internal_docs.items():
            col1, col2 = st.columns([3, 3])
            with col1:
                st.markdown(f"**{label}**")
            with col2:
                # Mostrar archivos existentes (si ya fueron cargados)
                doc_type_lookup = {
                    "empresa": 6 if profile_id == 1 else 9,
                    "vinculacion": 7 if profile_id == 1 else 10,
                    "seguridad": 8 if profile_id == 1 else 11
                }

                doc_type_id = doc_type_lookup[key_suffix]
                already_internal = get_uploaded_documents_map(session, request_id).get(doc_type_id, [])

                if already_internal:
                    for d in already_internal:
                        fecha = (
                            _to_colombia_tz(d["uploaded_at"]).strftime("%Y-%m-%d %H:%M")
                            if d.get("uploaded_at") else "sin fecha"
                        )
                        st.markdown(f"- [{d['file_name']}]({d['drive_link']}) • _{d['uploaded_by']}, {fecha}_")
                else:
                    st.caption("No cargado aún")

                uploaded_buffers[f"internal_{key_suffix}"] = st.file_uploader(
                    label="Subir archivo",
                    type=["pdf"],
                    key=f"uploader_internal_{key_suffix}_{request_id}",
                    accept_multiple_files=True
                )

        st.markdown("")
        st.markdown("**Estatus general del registro interno:**")
        current_internal_status = get_internal_status(session, request_id)
        default_index = 0
        if current_internal_status:
            # Busca el índice del estado actual dentro de la lista
            for i, label in enumerate(status_labels):
                if status_map[label] == current_internal_status:
                    default_index = i
                    break
        
        internal_status_label = st.selectbox(
            "Estado del Registro Interno",
            status_labels,
            index=default_index,
            key=f"status_internal_{request_id}"
        )


        st.markdown("---")

        # ====================================
        # ⚓ BLOQUE ADUANAS / PUERTOS / NAVIERAS
        # ====================================
        required_docs = get_required_document_types(session, profile_id)
        uploaded_map = get_uploaded_documents_map(session, request_id)
        lines = get_shipping_lines_status(session, request_id)
        ports = get_ports_status(session, request_id)
        customs = get_customs_status(session, request_id)

        for doc in required_docs:
            doc_id = doc["id"]
            doc_name = doc["name"]

            if any(keyword in doc_name.lower() for keyword in ["empresa", "vinculación", "vinculacion", "seguridad"]):
                continue

            already = uploaded_map.get(doc_id, [])

            st.markdown(f"#### {doc_name}")

            # ---- uploader único ----
            uploaded_buffers[doc_id] = st.file_uploader(
                label="Subir documento",
                type=["pdf"],
                key=f"uploader_{request_id}_{doc_id}",
                accept_multiple_files=True
            )

            # Mostrar archivos existentes
            if already:
                for d in already:
                    fecha = (
                        _to_colombia_tz(d["uploaded_at"]).strftime("%Y-%m-%d %H:%M")
                        if d.get("uploaded_at") else "sin fecha"
                    )
                    st.markdown(f"- [{d['file_name']}]({d['drive_link']}) • _{d['uploaded_by']}, {fecha}_")
            else:
                st.caption("No cargado aún")

            # ---- Estados asociados según tipo ----
            with st.expander("Estados asociados", expanded=True):
                if "aduanero" in doc_name.lower() and customs:
                    for c in customs:
                        col1, col2 = st.columns([3, 2])
                        with col1:
                            st.write(f"**{c.customs_name}**")
                        with col2:
                            # Calcula el índice del estado actual
                            current_index = 0
                            if c.status_id:
                                for i, label in enumerate(status_labels):
                                    if status_map[label] == c.status_id:
                                        current_index = i
                                        break

                            st.selectbox(
                                "Estado",
                                status_labels,
                                index=current_index,
                                key=f"status_customs_{c.customs_name}"
                            )


                # 🔹 Puertos y terminales
                elif "puerto" in doc_name.lower() and ports:
                    grouped_ports = {}
                    for p in ports:
                        grouped_ports.setdefault(p.port_name, []).append(p)
                    for port, terminals in grouped_ports.items():
                        for term in terminals:
                            name = f"{port} / {term.terminal_name or '(sin terminal)'}"
                            col1, col2 = st.columns([3, 2])
                            with col1:
                                st.write(name)
                            with col2:
                                st.selectbox(
                                    "Estado",
                                    status_labels,
                                    index=(term.status_id - 1) if term.status_id else 0,
                                    key=f"status_port_{term.id}"
                                )

                # 🔹 Líneas navieras
                elif "naviera" in doc_name.lower() and lines:
                    for line in lines:
                        col1, col2 = st.columns([3, 2])
                        with col1:
                            st.write(line.line_name)
                        with col2:
                            st.selectbox(
                                "Estado",
                                status_labels,
                                index=(line.status_id - 1) if line.status_id else 0,
                                key=f"status_line_{line.id}"
                            )

                else:
                    st.caption("Sin estados asociados a este tipo de documento.")

            st.markdown("---")

        # ====================================
        # 🧭 SEGUIMIENTO Y COMENTARIOS
        # ====================================
        st.subheader("Seguimiento y comentarios")

        meta = get_request_meta(session, request_id) or {}
        notif_default = (meta.get("notification_followup") or "").strip()
        comments_default = (meta.get("general_comments") or "").strip()

        seguimiento_text = st.text_area(
            "Seguimiento de notificación",
            value=notif_default,
            height=150
        )

        comentarios_text = st.text_area(
            "Comentarios generales",
            value=comments_default,
            height=150
        )

        # ====================================
        # 💾 GUARDAR TODO
        # ====================================
        if st.button("Guardar documentos y estados", key=f"btn_guardar_{request_id}"):
            with st.spinner("Guardando cambios..."):
                import tempfile
                try:
                    service = init_drive()
                    shared_drive_id = st.secrets["drive"].get("shared_drive_id")
                    parent_folder_id = st.secrets["drive"].get("parent_folder_id")

                    CLIENTS_FOLDER_ID = st.secrets["drive"].get("clients_folder_id")
                    PROVIDERS_FOLDER_ID = st.secrets["drive"].get("providers_folder_id")

                    # Detectar tipo de entidad según perfil
                    entity_type = "proveedor" if "proveedor" in profile_name.lower() else "cliente"

                    # Seleccionar carpeta base según tipo
                    base_folder_id = CLIENTS_FOLDER_ID if entity_type == "cliente" else PROVIDERS_FOLDER_ID

                    # Crear (o buscar) la subcarpeta específica
                    folder_id = find_or_create_folder(
                        service,
                        company_name,           # Nombre de la empresa
                        entity_type=entity_type,
                        base_folder_id=base_folder_id
                    )


                    # 🔹 Mapeo de tipos de documento internos según perfil
                    internal_doc_type_map = {
                        1: {"empresa": 6, "vinculacion": 7, "seguridad": 8},
                        2: {"empresa": 9, "vinculacion": 10, "seguridad": 11}
                    }

                    changes = 0

                    # === Subida de todos los documentos (incluido Registro Interno) ===
                    for key, files in uploaded_buffers.items():
                        if not files:
                            continue

                        # 🔸 Siempre convertir a lista (por si un uploader devuelve 1 archivo)
                        if not isinstance(files, list):
                            files = [files]

                        for file in files:
                            if not file:
                                continue

                            safe_name = sanitize_filename(file.name)

                            # 📂 Crear archivo temporal seguro
                            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{safe_name}") as tmp_file:
                                tmp_path = tmp_file.name
                                tmp_file.write(file.getbuffer())

                            drive_link = upload_to_drive(service, folder_id, tmp_path, safe_name)

                            # 🔸 Determinar tipo de documento
                            doc_type_id = None
                            if isinstance(key, str) and key.startswith("internal_"):
                                key_suffix = key.replace("internal_", "")
                                doc_type_id = internal_doc_type_map.get(profile_id, {}).get(key_suffix)
                            elif isinstance(key, int):
                                doc_type_id = key
                            else:
                                st.warning(f"⚠️ Clave inesperada en uploaded_buffers: {key} (tipo {type(key).__name__})")
                                os.remove(tmp_path)
                                continue

                            if not doc_type_id:
                                st.warning(f"⚠️ No se encontró un ID válido de tipo de documento para {key}")
                                os.remove(tmp_path)
                                continue

                            # 🔹 Guardar registro en BD
                            upsert_uploaded_document(
                                session,
                                request_id,
                                doc_type_id,
                                safe_name,
                                drive_link,
                                "system",
                                razon_social,
                                fecha_creacion
                            )

                            os.remove(tmp_path)
                            changes += 1

                    # === Guardar estatus de Registro Interno ===
                    upsert_status(session, "internal_registration", request_id, "Registro interno", status_map[internal_status_label])

                    # === Guardar estados asociados ===
                    for key, value in st.session_state.items():
                        if key.startswith("status_line_"):
                            record_id = int(key.replace("status_line_", ""))
                            line_data = next((l for l in lines if l.id == record_id), None)
                            if line_data:
                                upsert_status(
                                    session,
                                    "shipping_line_registration",
                                    request_id,
                                    line_data.line_name,   # ✅ usa el nombre real
                                    status_map[value]
                                )

                        elif key.startswith("status_port_"):
                            record_id = int(key.replace("status_port_", ""))
                            port_data = next((p for p in ports if p.id == record_id), None)
                            if port_data:
                                upsert_status(
                                    session,
                                    "port_registration",
                                    request_id,
                                    port_data.port_name,
                                    status_map[value],
                                    port_data.terminal_name
                                )

                        elif key.startswith("status_customs_"):
                            name = key.replace("status_customs_", "")
                            upsert_status(session, "customs_registration", request_id, name, status_map[value])

                    # === Guardar comentarios ===
                    update_request_meta(session, request_id, seguimiento_text, comentarios_text)

                    session.commit()
                    st.success(f"✅ Cambios guardados correctamente. {changes} documento(s) nuevo(s) agregado(s).")

                except Exception as e:
                    session.rollback()
                    st.error(f"❌ Error al guardar: {e}")

    finally:
        session.close()
