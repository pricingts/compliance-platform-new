# form_documents_existing.py

import os
import tempfile
import unicodedata
import streamlit as st
from datetime import datetime
from database.db import SessionLocal
from database.crud.documents import (
    get_requests_by_company_and_profile,
    get_required_document_types,
    get_uploaded_documents_map,
    get_all_statuses,
    get_shipping_lines_status,
    get_ports_status,
    get_customs_status,
    get_internal_status,
    get_request_meta,
    get_request_creation_date,
    upsert_uploaded_document,
    upsert_status,
    upsert_request_info,
    update_request_meta,
    insert_comment_entry,
    get_comment_entries,
)
from utils.form_helpers import cached_company_names, cached_profiles_list, cached_profile_id
from utils.timezone import to_colombia_tz
from utils.ui_helpers import render_section_header
from utils.error_handlers import handle_error
from services.audit import log_action
from services.logging_config import get_logger

# Google Drive utils
from services.google_drive_utils import init_drive, find_or_create_folder, upload_to_drive

logger = get_logger(__name__)

# ==========================
# FUNCIONES AUXILIARES
# ==========================

# Internal document type ID mappings by profile ID
# (these are specific to the upload form and differ from config.constants)
_INTERNAL_DOC_TYPE_MAP = {
    1: {"empresa": 6, "vinculacion": 7, "seguridad": 8},
    2: {"empresa": 9, "vinculacion": 10, "seguridad": 11},
}


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()


def is_security_verification(doc_name: str) -> bool:
    return "verificaciones de seguridad" in _slug(doc_name)


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

    # === Lineas navieras
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


# ==========================
# PRIVATE HELPER FUNCTIONS
# ==========================

def _render_company_profile_selector(session):
    """Render company/profile selectbox pair.

    Returns (company_name, profile_name, profile_id) or None if not selected.
    """
    companies = cached_company_names()
    profiles = cached_profiles_list()

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
        return None

    profile_id = cached_profile_id(profile_name)
    if not profile_id:
        st.error("❌ El perfil seleccionado no existe.")
        return None

    return (company_name, profile_name, profile_id)


def _render_request_selector(session, company_name, profile_id):
    """Render request dropdown filtered by company+profile.

    Returns selected request_id or None.
    """
    requests = get_requests_by_company_and_profile(session, company_name, profile_id)
    if not requests:
        st.warning("No hay solicitudes para esta compañía y perfil.")
        return None

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
            return None

    selected_request = requests[idx if len(options) > 1 else 0]
    return selected_request["id"]


def _render_base_data(request_id, session):
    """Render razon_social and fecha_creacion inputs.

    Returns (razon_social, fecha_creacion).
    """
    existing_fecha = get_request_creation_date(session, request_id)

    col1, col2 = st.columns(2)
    with col1:
        razon_key = f"razon_social_{request_id}"
        razon_social = st.text_input(
            "Razón Social",
            value=st.session_state.get(razon_key, ""),
            key=razon_key,
            placeholder="Ingresa la razón social del cliente"
        )

    with col2:
        fecha_key = f"fecha_creacion_{request_id}"
        fecha_creacion = st.date_input(
            "Fecha de Creación",
            value=st.session_state.get(fecha_key, existing_fecha or datetime.now().date()),
            key=fecha_key
        )

    return (razon_social, fecha_creacion)


def _render_internal_docs(session, profile_id, request_id, status_map, status_labels):
    """Render internal document uploaders: empresa, vinculacion, seguridad.

    Returns (uploaded_buffers dict, internal_status_label).
    """
    st.markdown("### Registro interno")
    uploaded_buffers = {}

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
            doc_type_id = _INTERNAL_DOC_TYPE_MAP.get(profile_id, {}).get(key_suffix)

            already_internal = get_uploaded_documents_map(session, request_id).get(doc_type_id, [])

            if already_internal:
                for d in already_internal:
                    fecha = (
                        to_colombia_tz(d["uploaded_at"]).strftime("%Y-%m-%d %H:%M")
                        if d.get("uploaded_at") else "sin fecha"
                    )
                    st.markdown(f"- [{d['file_name']}]({d['drive_link']}) • _{d['uploaded_by']}, {fecha}_")
            else:
                st.caption("No cargado aún")

            uploaded_buffers[f"internal_{key_suffix}"] = st.file_uploader(
                label="Subir archivo",
                type=["pdf", "jpg", "jpeg", "png"],
                key=f"uploader_internal_{key_suffix}_{request_id}",
                accept_multiple_files=True
            )

    st.markdown("")
    st.markdown("**Estatus general del registro interno:**")
    current_internal_status = get_internal_status(session, request_id)
    default_index = 0
    if current_internal_status:
        # Busca el indice del estado actual dentro de la lista
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

    return (uploaded_buffers, internal_status_label)


def _render_required_docs(session, profile_id, request_id, status_map, status_labels):
    """Render profile-required document uploaders + status controls.

    Returns uploaded_buffers dict (keyed by doc_type_id).
    """
    required_docs = get_required_document_types(session, profile_id)
    uploaded_map = get_uploaded_documents_map(session, request_id)
    lines = get_shipping_lines_status(session, request_id)
    ports = get_ports_status(session, request_id)
    customs = get_customs_status(session, request_id)

    uploaded_buffers = {}

    for doc in required_docs:
        doc_id = doc["id"]
        doc_name = doc["name"]

        if any(keyword in doc_name.lower() for keyword in ["empresa", "vinculación", "vinculacion", "seguridad"]):
            continue

        already = uploaded_map.get(doc_id, [])

        st.markdown(f"#### {doc_name}")

        # ---- uploader unico ----
        uploaded_buffers[doc_id] = st.file_uploader(
            label="Subir documento",
            type=["pdf", "jpg", "jpeg", "png"],
            key=f"uploader_{request_id}_{doc_id}",
            accept_multiple_files=True
        )

        # Mostrar archivos existentes
        if already:
            for d in already:
                fecha = (
                    to_colombia_tz(d["uploaded_at"]).strftime("%Y-%m-%d %H:%M")
                    if d.get("uploaded_at") else "sin fecha"
                )
                st.markdown(f"- [{d['file_name']}]({d['drive_link']}) • _{d['uploaded_by']}, {fecha}_")
        else:
            st.caption("No cargado aún")

        # ---- Estados asociados segun tipo ----
        with st.expander("Estados asociados", expanded=True):
            if "aduanero" in doc_name.lower() and customs:
                for c in customs:
                    col1, col2 = st.columns([3, 2])
                    with col1:
                        st.write(f"**{c.customs_name}**")
                    with col2:
                        # Calcula el indice del estado actual
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

            # Puertos y terminales
            elif "puerto" in doc_name.lower() and ports:
                grouped_ports = {}
                for p in ports:
                    grouped_ports.setdefault(p.port_name, []).append(p)
                for port, terminals in grouped_ports.items():
                    for term in terminals:
                        name = f"{port} / {term.terminal_name or '(sin terminal)'}"
                        col1, col2 = st.columns([3, 2])
                        with col1:
                            st.write(f"**{name}**")
                        with col2:
                            st.selectbox(
                                "Estado",
                                status_labels,
                                index=(term.status_id - 1) if term.status_id else 0,
                                key=f"status_port_{term.id}"
                            )

            # Lineas navieras
            elif "naviera" in doc_name.lower() and lines:
                for line in lines:
                    col1, col2 = st.columns([3, 2])
                    with col1:
                        st.write(f"**{line.line_name}**")
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

    return uploaded_buffers


def _render_followup_section(request_id, session):
    """Render threaded comment history + new comment input.

    Returns (notifications, comments) for backward-compat with legacy
    comments table, plus handles new comment_entries insertion.
    """
    st.subheader("Seguimiento y comentarios")

    # --- Display existing threaded comments ---
    entries = get_comment_entries(session, request_id)
    if entries:
        for entry in entries:
            created = entry["created_at"]
            date_str = (
                to_colombia_tz(created).strftime("%Y-%m-%d %H:%M")
                if created else "sin fecha"
            )
            author = entry["author_name"] or entry["author_email"]
            entry_type = entry["entry_type"]

            type_icon = {"comment": "", "rechazo": " [RECHAZO]", "nota": " [NOTA]"}.get(entry_type, "")

            st.markdown(
                f"**{author}**{type_icon} - _{date_str}_\n\n"
                f"> {entry['content']}"
            )

            # Show image thumbnail if present
            if entry.get("image_drive_link"):
                img_name = entry.get("image_file_name", "imagen")
                st.markdown(f"[{img_name}]({entry['image_drive_link']})")

            st.markdown("---")
    else:
        st.caption("Sin comentarios registrados.")

    # --- New comment input ---
    st.markdown("**Agregar comentario:**")
    new_comment = st.text_area(
        "Escribe un comentario",
        height=100,
        key=f"new_comment_{request_id}",
        placeholder="Escribe un comentario o nota de seguimiento..."
    )

    comment_type = st.selectbox(
        "Tipo",
        ["comment", "nota"],
        format_func=lambda x: {"comment": "Comentario", "nota": "Nota de seguimiento"}.get(x, x),
        key=f"comment_type_{request_id}",
    )

    comment_image = st.file_uploader(
        "Adjuntar imagen (opcional)",
        type=["jpg", "jpeg", "png"],
        key=f"comment_image_{request_id}",
    )

    # Store new comment data in session_state for processing in _save_all_data
    st.session_state[f"_pending_comment_{request_id}"] = {
        "text": new_comment,
        "type": comment_type,
        "image": comment_image,
    }

    # --- Legacy follow-up fields (backward compat) ---
    meta = get_request_meta(session, request_id) or {}
    notif_default = (meta.get("notification_followup") or "").strip()
    comments_default = (meta.get("general_comments") or "").strip()

    with st.expander("Campos legacy (seguimiento / notificaciones)", expanded=False):
        seguimiento_text = st.text_area(
            "Seguimiento de notificacion",
            value=notif_default,
            height=100
        )
        comentarios_text = st.text_area(
            "Comentarios generales (legacy)",
            value=comments_default,
            height=100
        )

    return (seguimiento_text, comentarios_text)


def _upload_files_to_drive(service, folder_id, uploaded_buffers, profile_id):
    """Upload files to Google Drive.

    Returns (list of (doc_type_id, safe_name, drive_link), changes_count).
    """
    results = []
    changes = 0

    for key, files in uploaded_buffers.items():
        if not files:
            continue

        # Siempre convertir a lista (por si un uploader devuelve 1 archivo)
        if not isinstance(files, list):
            files = [files]

        for file in files:
            if not file:
                continue

            safe_name = sanitize_filename(file.name)

            # Crear archivo temporal seguro
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{safe_name}") as tmp_file:
                    tmp_path = tmp_file.name
                    tmp_file.write(file.getbuffer())

                drive_link = upload_to_drive(service, folder_id, tmp_path, safe_name)

                # Determinar tipo de documento
                doc_type_id = None
                if isinstance(key, str) and key.startswith("internal_"):
                    key_suffix = key.replace("internal_", "")
                    doc_type_id = _INTERNAL_DOC_TYPE_MAP.get(profile_id, {}).get(key_suffix)
                elif isinstance(key, int):
                    doc_type_id = key
                else:
                    st.warning(f"Clave inesperada en uploaded_buffers: {key} (tipo {type(key).__name__})")
                    continue

                if not doc_type_id:
                    st.warning(f"No se encontro un ID valido de tipo de documento para {key}")
                    continue

                results.append((doc_type_id, safe_name, drive_link))
                changes += 1
            except Exception as e:
                logger.exception(f"Drive upload failed for {safe_name}")
                st.error(f"Error al subir {safe_name}: {e}")
                # Continue with next file instead of aborting
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

    return (results, changes)


def _save_all_data(
    session, request_id, uploaded_results, razon_social, fecha_creacion,
    notifications, comments, internal_status_label, status_map,
    lines, ports, customs, uploaded_by
):
    """DB persistence: upsert docs + statuses + meta."""
    user_email = getattr(st.user, "email", None) if hasattr(st, "user") else None

    for doc_type_id, safe_name, drive_link in uploaded_results:
        upsert_uploaded_document(
            session,
            request_id,
            doc_type_id,
            safe_name,
            drive_link,
            uploaded_by,
            razon_social,
            fecha_creacion,
            user_email=user_email,
        )

    razon_social_val = st.session_state.get(f"razon_social_{request_id}", "").strip()
    fecha_creacion_val = st.session_state.get(f"fecha_creacion_{request_id}", datetime.now().date())
    upsert_request_info(
        session,
        request_id,
        uploaded_by,
        razon_social_val,
        fecha_creacion_val
    )

    # === Guardar estatus de Registro Interno ===
    upsert_status(session, "internal_registration", request_id, "Registro interno", status_map[internal_status_label], user_email=user_email)

    # === Guardar estados asociados ===
    for key, value in st.session_state.items():
        if key.startswith("status_line_"):
            record_id = int(key.replace("status_line_", ""))
            line_data = next((ln for ln in lines if ln.id == record_id), None)
            if line_data:
                upsert_status(
                    session,
                    "shipping_line_registration",
                    request_id,
                    line_data.line_name,
                    status_map[value],
                    user_email=user_email,
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
                    port_data.terminal_name,
                    user_email=user_email,
                )

        elif key.startswith("status_customs_"):
            name = key.replace("status_customs_", "")
            upsert_status(session, "customs_registration", request_id, name, status_map[value], user_email=user_email)

    # === Guardar comentarios legacy ===
    update_request_meta(session, request_id, notifications, comments)

    # === Guardar nuevo comentario (threaded) ===
    pending = st.session_state.get(f"_pending_comment_{request_id}", {})
    comment_text = (pending.get("text") or "").strip()
    if comment_text and user_email:
        image_link = None
        image_name = None

        # Upload comment image to Drive if present
        comment_image = pending.get("image")
        if comment_image:
            try:
                service = init_drive()
                CLIENTS_FOLDER_ID = st.secrets["drive"].get("clients_folder_id")
                safe_img_name = sanitize_filename(comment_image.name)
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{safe_img_name}") as tmp:
                        tmp_path = tmp.name
                        tmp.write(comment_image.getbuffer())
                    image_link = upload_to_drive(service, CLIENTS_FOLDER_ID, tmp_path, safe_img_name)
                    image_name = safe_img_name
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.remove(tmp_path)
            except Exception as e:
                logger.warning(f"Failed to upload comment image: {e}")

        insert_comment_entry(
            session=session,
            request_id=request_id,
            author_email=user_email,
            author_name=uploaded_by,
            content=comment_text,
            entry_type=pending.get("type", "comment"),
            image_drive_link=image_link,
            image_file_name=image_name,
        )

        log_action(
            session=session,
            user_email=user_email,
            action="CREATE",
            entity_type="comment_entry",
            entity_id=request_id,
            new_value={"content": comment_text[:200], "type": pending.get("type", "comment")},
            details=f"Request #{request_id}: new comment",
        )

    # Audit: log legacy comment update
    if user_email and (notifications or comments):
        log_action(
            session=session,
            user_email=user_email,
            action="UPDATE",
            entity_type="comments",
            entity_id=request_id,
            new_value={"notifications": notifications or "", "comments": comments or ""},
            details=f"Request #{request_id}: updated comments/notifications",
        )

    try:
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to commit upload form data")
        raise


def forms():
    """Main form orchestrator for document upload."""
    st.subheader("📎 Carga de documentos")

    session = SessionLocal()

    try:
        # === Company and profile selection ===
        render_section_header("1. Seleccion de Solicitud")
        result = _render_company_profile_selector(session)
        if result is None:
            return
        company_name, profile_name, profile_id = result

        # === Request selection ===
        request_id = _render_request_selector(session, company_name, profile_id)
        if request_id is None:
            return

        # === Base data (razon social, fecha) ===
        render_section_header("2. Datos Base")
        razon_social, fecha_creacion = _render_base_data(request_id, session)

        status_map = get_all_statuses(session)
        status_labels = list(status_map.keys())

        # === Internal documents block ===
        render_section_header("3. Documentos Internos")
        internal_buffers, internal_status_label = _render_internal_docs(
            session, profile_id, request_id, status_map, status_labels
        )

        # === Required documents block (aduanas / puertos / navieras) ===
        render_section_header("4. Documentos Requeridos")
        required_buffers = _render_required_docs(
            session, profile_id, request_id, status_map, status_labels
        )

        # Merge all uploaded buffers
        uploaded_buffers = {**internal_buffers, **required_buffers}

        # === Followup and comments ===
        render_section_header("5. Seguimiento y Comentarios")
        seguimiento_text, comentarios_text = _render_followup_section(request_id, session)

        # === Save everything ===
        if st.button("Guardar documentos y estados", key=f"btn_guardar_{request_id}"):
            try:
                service = init_drive()

                CLIENTS_FOLDER_ID = st.secrets["drive"].get("clients_folder_id")
                PROVIDERS_FOLDER_ID = st.secrets["drive"].get("providers_folder_id")

                # Detectar tipo de entidad segun perfil
                entity_type = "proveedor" if "proveedor" in profile_name.lower() else "cliente"

                # Seleccionar carpeta base segun tipo
                base_folder_id = CLIENTS_FOLDER_ID if entity_type == "cliente" else PROVIDERS_FOLDER_ID

                # Crear (o buscar) la subcarpeta especifica
                folder_id = find_or_create_folder(
                    service,
                    company_name,
                    entity_type=entity_type,
                    base_folder_id=base_folder_id
                )

                # Upload files to Drive
                with st.spinner("Subiendo documentos a Google Drive..."):
                    uploaded_results, changes = _upload_files_to_drive(
                        service, folder_id, uploaded_buffers, profile_id
                    )

                # Re-fetch status entities for save (needed for session_state iteration)
                lines = get_shipping_lines_status(session, request_id)
                ports = get_ports_status(session, request_id)
                customs = get_customs_status(session, request_id)

                # Persist everything to DB
                with st.spinner("Guardando datos..."):
                    _save_all_data(
                        session, request_id, uploaded_results,
                        razon_social, fecha_creacion,
                        seguimiento_text, comentarios_text,
                        internal_status_label, status_map,
                        lines, ports, customs,
                        st.user.name
                    )

                st.success(f"Cambios guardados correctamente. {changes} documento(s) nuevo(s) agregado(s).")

            except Exception as e:
                session.rollback()
                logger.exception("Error saving upload form data")
                handle_error(e, "Error al guardar los datos.")

    finally:
        session.close()
