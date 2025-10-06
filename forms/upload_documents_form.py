# form_documents_existing.py

import os
import unicodedata
import streamlit as st
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from database.db import SessionLocal
from database.crud.documents import (
    get_all_company_names,
    get_profiles_list,
    get_profile_id_by_name,
    get_requests_by_company_and_profile,
    get_required_document_types,
    get_uploaded_documents_map,
    upsert_uploaded_document,
    get_request_meta,
    update_request_meta
)
from services.google_drive_utils import init_drive, find_or_create_folder, upload_to_drive

CO_TZ = ZoneInfo("America/Bogota")

def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().lower()


def is_security_verification(doc_name: str) -> bool:
    return "verificaciones de seguridad" in _slug(doc_name)

def split_csv_list(s: str):
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x and x.strip()]

def sanitize_name_for_csv(name: str) -> str:
    return name.replace(",", " - ").replace("/", "_").replace("\\", "_").strip()


def _to_colombia_tz(dt: datetime | None) -> datetime | None:

    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CO_TZ)


def forms():
    st.subheader("📎 Carga de documentos")

    session = SessionLocal()

    try:
        companies = get_all_company_names(session)
        profiles = get_profiles_list(session)

        col1, col2 = st.columns(2)
        with col1:
            company_name = st.selectbox(
                "Nombre de la compañía",
                companies,
                index=None if companies else None,
                placeholder="Selecciona la compañía...",
                key="company_selector"
            )
        with col2:
            profile_name = st.selectbox(
                "Perfil",
                profiles,
                index=None if profiles else None,
                placeholder="Selecciona el perfil...",
                key="profile_selector"
            )

        if not company_name or not profile_name:
            st.info("Selecciona una compañía y un perfil para continuar.")
            return

        profile_id = get_profile_id_by_name(session, profile_name)
        if not profile_id:
            st.error("❌ El perfil seleccionado no existe en la base de datos.")
            return

        # 2) Buscar solicitudes existentes por compañía + perfil
        requests = get_requests_by_company_and_profile(session, company_name, profile_id)
        if not requests:
            st.warning("No hay solicitudes para esta compañía y perfil. Crea primero una solicitud en el formulario de registro.")
            return

        options = [f"ID {r['id']} • {r['created_at'].strftime('%Y-%m-%d %H:%M')}" for r in requests]
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


        required_docs = get_required_document_types(session, profile_id)
        uploaded_map = get_uploaded_documents_map(session, request_id)

        st.caption("Sube los documentos. Los ya subidos muestran enlace.")
        uploaded_buffers = {}
        pending_count = 0

        for doc in required_docs:
            doc_id = doc["id"]
            doc_name = doc["name"]
            already = uploaded_map.get(doc_id)
            link_csv = already.get("drive_link") if already else None
            names_csv = already.get("file_name") if already else ""

            allow_multi = is_security_verification(doc_name)

            if allow_multi:
                # Mostrar múltiples links si existen (CSV)
                urls = split_csv_list(link_csv) if link_csv else []
                names = split_csv_list(names_csv) if names_csv else []
                if urls:
                    st.markdown(f"✅ **{doc_name}** — {len(urls)} archivo(s):")
                    for i, u in enumerate(urls):
                        label = names[i] if i < len(names) else f"Archivo {i+1}"
                        st.markdown(f"- [{label}]({u})")
                else:
                    st.markdown(f"❌ **{doc_name}** — No cargado")
            else:
                # Comportamiento normal 1:1
                if link_csv:
                    st.markdown(f"✅ **{doc_name}** — [Ver archivo]({link_csv})")
                    continue
                else:
                    req_mark = " (obligatorio)" if doc.get("is_required") else ""
                    st.markdown(f"❌ **{doc_name}**{req_mark} — No cargado")

            # Uploader (múltiple solo para verificaciones)
            uploaded_buffers[doc_id] = st.file_uploader(
                label=f"📁 Subir {doc_name}",
                type=["pdf"],
                key=f"uploader_{request_id}_{doc_id}",
                accept_multiple_files=allow_multi
            )
            st.write("")  # espaciado

            # contar pendientes solo si no hay nada aún
            if allow_multi:
                urls = split_csv_list(link_csv) if link_csv else []
                if not urls:
                    pending_count += 1
            else:
                if not link_csv:
                    pending_count += 1

        # --- Seguimiento y comentarios (siempre visibles) ---
        st.markdown("---")
        st.subheader("🧭 Seguimiento y comentarios")

        meta = get_request_meta(session, request_id) or {}
        notif_default = (meta.get("notification_followup") or "").strip()
        comments_default = (meta.get("general_comments") or "").strip()

        seguimiento_text = st.text_area(
            "Seguimiento de notificación",
            value=notif_default,
            placeholder="Ej.: 2025-08-20: Enviado correo a contacto@empresa.com\n2025-08-22: Respondieron adjuntando doc. pendiente...",
            key=f"seguimiento_{request_id}",
            height=150
        )

        comentarios_text = st.text_area(
            "Comentarios generales",
            value=comments_default,
            placeholder="Observaciones generales de la solicitud / riesgos / acuerdos / notas internas.",
            key=f"comentarios_{request_id}",
            height=150
        )

        # Botón único: guarda documentos (si hay) y notas SIEMPRE
        label_btn = "Guardar documentos y notas" if pending_count > 0 else "Guardar notas"
        if st.button(label_btn, key=f"btn_guardar_integrado_{request_id}"):
            with st.spinner("Guardando cambios..."):
                try:
                    changes = 0

                    # 1) Subir documentos seleccionados (si hay alguno)
                    any_file_selected = any(bool(uploaded_buffers.get(d["id"])) for d in required_docs)
                    if any_file_selected:
                        service = init_drive()
                        shared_drive_id = st.secrets["drive"].get("shared_drive_id")
                        parent_folder_id = st.secrets["drive"].get("parent_folder_id")

                        folder_name = f"Solicitud - {company_name} - {profile_name}"
                        folder_id = find_or_create_folder(
                            service,
                            folder_name,
                            shared_drive_id=shared_drive_id if not parent_folder_id else None,
                            parent_folder_id=parent_folder_id,
                        )

                        for doc in required_docs:
                            doc_id = doc["id"]
                            doc_name = doc["name"]
                            files = uploaded_buffers.get(doc_id)

                            if not files:
                                continue

                            # Normaliza a lista (si no es múltiple, Streamlit retorna UploadedFile)
                            if not isinstance(files, list):
                                files = [files]

                            if is_security_verification(doc_name):
                                # Cargar listas existentes (CSV) si las hubiera
                                already = uploaded_map.get(doc_id)
                                existing_links = split_csv_list(already.get("drive_link") if already else "")
                                existing_names = split_csv_list(already.get("file_name") if already else "")

                                new_links, new_names = [], []

                                for i, file in enumerate(files):
                                    if file is None:
                                        continue

                                    safe_name = sanitize_name_for_csv(file.name)
                                    tmp_path = f"/tmp/{request_id}_{doc_id}_{i}_{safe_name}"
                                    with open(tmp_path, "wb") as f:
                                        f.write(file.getbuffer())

                                    drive_link = upload_to_drive(service, folder_id, tmp_path, safe_name)

                                    new_names.append(safe_name)
                                    new_links.append(drive_link)
                                    changes += 1

                                    try:
                                        os.remove(tmp_path)
                                    except Exception:
                                        pass

                                # Unir existentes + nuevas en CSV
                                all_names = existing_names + new_names
                                all_links = existing_links + new_links

                                upsert_uploaded_document(
                                    session=session,
                                    request_id=request_id,
                                    document_type_id=doc_id,
                                    file_name=", ".join(all_names),
                                    drive_link=", ".join(all_links),
                                    uploaded_by=(getattr(st, "user", None).name if getattr(st, "user", None) else "system")
                                )

                            else:
                                # Documentos normales: 1:1 (si suben varios por error, se usará el último upsert)
                                for i, file in enumerate(files):
                                    if file is None:
                                        continue

                                    safe_name = file.name.replace("/", "_").replace("\\", "_")
                                    tmp_path = f"/tmp/{request_id}_{doc_id}_{i}_{safe_name}"
                                    with open(tmp_path, "wb") as f:
                                        f.write(file.getbuffer())

                                    drive_link = upload_to_drive(service, folder_id, tmp_path, safe_name)

                                    upsert_uploaded_document(
                                        session=session,
                                        request_id=request_id,
                                        document_type_id=doc_id,
                                        file_name=safe_name,
                                        drive_link=drive_link,
                                        uploaded_by=(getattr(st, "user", None).name if getattr(st, "user", None) else "system")
                                    )
                                    changes += 1

                                    try:
                                        os.remove(tmp_path)
                                    except Exception:
                                        pass

                    # 2) Guardar seguimiento y comentarios SIEMPRE
                    update_request_meta(session, request_id, seguimiento_text, comentarios_text)

                    session.commit()

                    if changes:
                        st.success(f"✅ {changes} documento(s) cargado(s)/actualizado(s) y notas guardadas.")
                    else:
                        st.success("✅ Notas guardadas.")

                except Exception as e:
                    session.rollback()
                    st.error(f"❌ Error al guardar: {e}")

        # Mensaje informativo si no hay pendientes
        if pending_count == 0:
            st.info("No hay documentos pendientes por subir. Puedes actualizar las notas y guardarlas.")

    finally:
        session.close()
