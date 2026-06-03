import streamlit as st
from googleapiclient.errors import HttpError
from gspread.exceptions import GSpreadException
from sqlalchemy.exc import SQLAlchemyError
from database.db import SessionLocal
from database.crud.clientes import (
    insert_client_request,
    insert_customs_registration,
    insert_port_registration,
    insert_shipping_line_registration,
    get_profile_id,
)
from services.sheets_writer import save_request
from services.audit import log_action
from services.logging_config import get_logger
from utils.error_handlers import handle_error, sanitize_for_user
from utils.exceptions import DriveUploadError, MailerError, SheetsError
from utils.ui_helpers import render_section_header
from utils.validators import validate_emails, normalize_emails, sanitize_company_name
from config.constants import (
    TERMINALES,
    TRADING_COUNTRIES,
    OPERATION_TYPES,
    CUSTOMS_SYSTEMS,
    SHIPPING_LINES,
    PORTS,
    MSC_CONTAINER_TYPES,
    LANGUAGES,
    PROVIDER_TYPES,
    ALLOWED_ATTACHMENT_TYPES,
    REMINDER_FREQUENCY_OPTIONS,
    REMINDER_MAX_MONTHS_OPTIONS,
)

logger = get_logger(__name__)


def _is_sheets_enabled() -> bool:
    """Return True iff ``st.secrets['sheets']['enabled']`` is truthy.

    Default-off: once the Python mailer is handling notifications, the
    legacy Google Sheet write-through is redundant (and keeps the Apps
    Script notifier alive, duplicating the email). Operators can flip the
    flag back on to re-enable the Sheet for auditing or rollback.
    """
    try:
        cfg = st.secrets.get("sheets") if hasattr(st, "secrets") else None
    except (ImportError, FileNotFoundError, KeyError, AttributeError):
        return False
    if not cfg:
        return False
    return bool(cfg.get("enabled", False))


def _render_request_type_selector(session):
    """Render request type selectbox and look up the corresponding profile_id.

    Returns:
        tuple: (tipo_solicitud, profile_id) or (None, None) on error.
    """
    tipo_solicitud = st.selectbox(
        "Tipo de solicitud",
        ["cliente", "proveedor"],
        key="tipo_solicitud",
    )

    try:
        profile_id = get_profile_id(session, tipo_solicitud)
    except SQLAlchemyError as e:
        session.close()
        handle_error(e, "Error al conectar con la base de datos.")
        return None, None

    if not profile_id:
        session.close()
        st.error("El perfil seleccionado no existe en la base de datos.")
        return None, None

    return tipo_solicitud, profile_id


def _build_requester_data(
    current_user: dict,
    dropdown_value=None,
    text_input_value=None,
    assigned_comerciales=None,
    tipo_solicitud: str = "cliente",
) -> dict:
    """Pure function: decide what to put in the requester fields based on role.

    Args:
        current_user: dict with at least {email, nombre_display, rol}.
        dropdown_value: selected value from the comercial dropdown (only used
            when role is inside_sales).
        text_input_value: value from the proveedor name text input (only used
            for proveedor flow).
        assigned_comerciales: list of {email, nombre_display} for the IS user.
        tipo_solicitud: 'cliente' or 'proveedor'.

    Returns:
        dict with keys:
            valid (bool), error (str — only when valid=False),
            requested_by (str), requested_by_type (str),
            commercial (str|None), submitted_by_email (str|None).
    """
    assigned_comerciales = assigned_comerciales or []
    rol = current_user.get("rol", "otro")
    nombre = current_user.get("nombre_display") or current_user.get("email") or "unknown"
    email = current_user.get("email")

    # Provider flow: identical for every role — text_input + 'solicitante_proveedor' type.
    if tipo_solicitud.lower() == "proveedor":
        if not text_input_value:
            return {
                "valid": False,
                "error": "Debes ingresar el nombre de quien solicita (proveedor).",
                "requested_by": None,
                "requested_by_type": None,
                "commercial": None,
                "submitted_by_email": None,
            }
        return {
            "valid": True,
            "requested_by": text_input_value,
            "requested_by_type": "solicitante_proveedor",
            "commercial": None,
            "submitted_by_email": None,
        }

    # Cliente flow — branches by role
    if rol == "comercial":
        return {
            "valid": True,
            "requested_by": nombre,
            "requested_by_type": "comercial",
            "commercial": nombre,
            "submitted_by_email": None,
        }

    if rol == "inside_sales":
        if not assigned_comerciales:
            return {
                "valid": False,
                "error": (
                    "No tienes comerciales asignados. Contacta al administrador "
                    "para que te asigne al menos uno antes de crear solicitudes."
                ),
                "requested_by": None,
                "requested_by_type": None,
                "commercial": None,
                "submitted_by_email": None,
            }
        if not dropdown_value:
            return {
                "valid": False,
                "error": "Debes seleccionar el comercial para el que estás creando la solicitud.",
                "requested_by": None,
                "requested_by_type": None,
                "commercial": None,
                "submitted_by_email": None,
            }
        return {
            "valid": True,
            "requested_by": nombre,
            "requested_by_type": "inside_sales",
            "commercial": dropdown_value,
            "submitted_by_email": email,
        }

    # compliance / otro: no commercial field
    return {
        "valid": True,
        "requested_by": nombre,
        "requested_by_type": rol if rol in ("compliance", "otro") else "otro",
        "commercial": None,
        "submitted_by_email": None,
    }


def _render_requester_section(session, tipo_solicitud, current_user):
    """Render the requester input depending on request type AND role.

    Returns:
        dict — see _build_requester_data for shape.
    """
    from services.users import get_comerciales_for_inside_sales

    rol = current_user.get("rol", "otro")
    nombre = current_user.get("nombre_display") or current_user.get("email") or "Usuario"

    dropdown_value = None
    text_input_value = None
    assigned_comerciales = []

    if tipo_solicitud.lower() == "proveedor":
        text_input_value = st.text_input(
            "Nombre de quien solicita", key="solicitante_proveedor"
        )
    else:
        # cliente flow
        if rol == "comercial":
            st.text_input("Comercial", value=nombre, disabled=True, key="comercial_readonly")
        elif rol == "inside_sales":
            assigned_comerciales = get_comerciales_for_inside_sales(
                session, current_user.get("email")
            )
            if not assigned_comerciales:
                st.warning(
                    "No tienes comerciales asignados. Contacta al administrador."
                )
            else:
                options = [c["nombre_display"] for c in assigned_comerciales]
                dropdown_value = st.selectbox(
                    "Comercial al que apoya esta solicitud",
                    options,
                    key="comercial_for_is",
                )
        else:
            # compliance / otro: no commercial field
            st.info(f"Solicitud creada por: {nombre} (rol: {rol})")

    return _build_requester_data(
        current_user=current_user,
        dropdown_value=dropdown_value,
        text_input_value=text_input_value,
        assigned_comerciales=assigned_comerciales,
        tipo_solicitud=tipo_solicitud,
    )


def _render_company_info():
    """Render the 3-column layout with company fields.

    Returns:
        dict with keys: company_name, language, trading, email, location,
              reminder_frequency, reminder_frequency_days, reminder_max_months.
    """
    col1, col2, col3 = st.columns(3)
    with col1:
        company_name = st.text_input(
            "Nombre de la Compañía", key="nombre_compania"
        )
        language = st.selectbox(
            "¿Qué idioma hablan?", LANGUAGES, key="idioma_compania"
        )
    with col2:
        trading = st.selectbox(
            "Desde qué trading se va a crear",
            TRADING_COUNTRIES,
            key="trading_creacion",
        )
        email = st.text_input(
            "Correo(s) electrónico(s)",
            help="Puede ingresar varios separados por coma o punto y coma.",
            key="correo_compania",
        )
    with col3:
        location = st.text_input(
            "Pais de la Compañía a Registrar", key="ubicacion_compania"
        )

    # Phase 7: two independent reminder selectboxes.
    st.markdown("**Recordatorios**")
    rcol1, rcol2 = st.columns(2)
    with rcol1:
        reminder_frequency_label = st.selectbox(
            "Frecuencia de recordatorio",
            list(REMINDER_FREQUENCY_OPTIONS.keys()),
            key="reminder_frequency_label",
            help="Cada cuánto se enviará el recordatorio.",
        )
    with rcol2:
        reminder_max_months_label = st.selectbox(
            "Tiempo máximo de recordatorio",
            list(REMINDER_MAX_MONTHS_OPTIONS.keys()),
            key="reminder_max_months_label",
            help="Cuándo dejar de enviar recordatorios.",
        )

    reminder_frequency_days = REMINDER_FREQUENCY_OPTIONS[reminder_frequency_label]
    reminder_max_months = REMINDER_MAX_MONTHS_OPTIONS[reminder_max_months_label]

    return {
        "company_name": company_name,
        "language": language,
        "trading": trading,
        "email": email,
        "location": location,
        # Legacy field stored as the friendly label (e.g. 'Semanal') for
        # backward compatibility with sheets_writer and historical reports.
        "reminder_frequency": reminder_frequency_label,
        "reminder_frequency_days": reminder_frequency_days,
        "reminder_max_months": reminder_max_months,
    }


def _render_client_specifics():
    """Render client-specific fields: operation type, customs, ports, shipping lines.

    Returns:
        dict with keys: tipo_operacion, aduana, tipo_aduana, puerto,
              terminales_seleccionados, linea_naviera, tipo_linea,
              datos_msc, commodity.
    """
    aduana = False
    tipo_aduana = []
    puerto = False
    terminales_seleccionados = {}
    linea_naviera = False
    tipo_linea = []
    datos_msc = {}

    col4, col5 = st.columns(2)
    with col4:
        tipo_operacion = st.selectbox(
            "Tipo de Operacion", OPERATION_TYPES, key="tipo_operacion"
        )
        aduana = st.checkbox("Registro con Aduana", key="aduana")
        if aduana:
            tipo_aduana = st.multiselect(
                "Escoja la(s) aduana(s)", CUSTOMS_SYSTEMS, key="tipo_aduana"
            )

        linea_naviera = st.checkbox(
            "Registro con Linea Naviera", key="linea_naviera"
        )
        if linea_naviera:
            tipo_linea = st.multiselect(
                "Escoja la(s) línea(s) naviera(s)",
                SHIPPING_LINES,
                key="tipo_linea",
            )

            if "MSC" in tipo_linea:
                pol = st.text_input(
                    "POL (Puerto de Origen)", key="msc_pol"
                )
                pod = st.text_input(
                    "POD (Puerto de Destino)", key="msc_pod"
                )
                producto = st.text_input("Producto", key="msc_producto")
                tipo_contenedor = st.selectbox(
                    "Tipo de Contenedor",
                    MSC_CONTAINER_TYPES,
                    key="msc_tipo_contenedor",
                )
                shipper_bl = st.text_input(
                    "¿Cómo saldrá el Shipper en BL?", key="msc_shipper_bl"
                )

                datos_msc = {
                    "POL": pol,
                    "POD": pod,
                    "Producto": producto,
                    "Tipo de Contenedor": tipo_contenedor,
                    "Shipper en BL": shipper_bl,
                }
            else:
                datos_msc = {}

    with col5:
        commodity = st.text_input("Commodity", key="commodity")
        puerto = st.checkbox("Registro con Puerto", key="Puerto")
        if puerto:
            tipo_puerto = st.multiselect(
                "Escoja el/los puerto(s)",
                PORTS,
                key="tipo_puerto",
            )
            terminales_seleccionados = {}
            for p in tipo_puerto:
                if p in TERMINALES:
                    terminales = st.multiselect(
                        f"Seleccione terminal(es) para {p}",
                        TERMINALES[p],
                        key=f"terminal_{p}",
                    )
                    terminales_seleccionados[p] = terminales
                else:
                    terminales_seleccionados[p] = []

    return {
        "tipo_operacion": tipo_operacion,
        "aduana": aduana,
        "tipo_aduana": tipo_aduana,
        "puerto": puerto,
        "terminales_seleccionados": terminales_seleccionados,
        "linea_naviera": linea_naviera,
        "tipo_linea": tipo_linea,
        "datos_msc": datos_msc,
        "commodity": commodity,
    }


def _render_notes_and_attachments():
    """Phase 4: textarea for notes + multi-file uploader.

    Returns:
        tuple (notes_str, list_of_uploaded_files)
    """
    notes = st.text_area(
        "Notas para Compliance",
        max_chars=2000,
        help="Información adicional que el equipo de Compliance debe conocer (opcional).",
        key="request_notes",
        height=100,
    )
    files = st.file_uploader(
        "Adjuntos (PDF, JPG, PNG, DOCX, XLSX — máx 10 MB c/u)",
        type=ALLOWED_ATTACHMENT_TYPES,
        accept_multiple_files=True,
        key="request_attachments_files",
    )
    return notes, files or []


def _upload_attachments_to_drive(
    service,
    base_folder_id,
    entity_type: str,
    company_name: str,
    files: list,
    uploaded_by: str,
) -> list[dict]:
    """Upload attachments to {entity_type_folder}/{company}/Adjuntos Solicitud/.

    Returns a list of {file_name, drive_link} dicts for files that uploaded
    successfully. Errors per-file are surfaced via st.warning but do not
    abort the full upload.
    """
    import os
    import tempfile
    from services.google_drive_utils import (
        find_or_create_folder, find_or_create_subfolder, upload_to_drive,
    )
    from utils.validators import validate_file_size

    results: list[dict] = []
    if not files:
        return results

    try:
        company_folder_id = find_or_create_folder(
            service, company_name, entity_type=entity_type, base_folder_id=base_folder_id,
        )
        attachments_folder_id = find_or_create_subfolder(
            service, company_folder_id, "Adjuntos Solicitud",
        )
    except (HttpError, OSError, DriveUploadError) as e:
        logger.error("Failed to ensure attachments subfolder", extra={"error": str(e)})
        st.warning(
            sanitize_for_user(
                e,
                default="No se pudo crear la carpeta de adjuntos en Drive.",
            )
        )
        return results

    for f in files:
        if not validate_file_size(f):
            st.warning(f"Archivo {f.name} excede 10 MB — omitido.")
            continue
        # Reuse the existing sanitize_filename helper
        from forms.upload_documents_form import sanitize_filename
        safe_name = sanitize_filename(f.name)
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(f.name)[1]) as tmp:
                tmp.write(f.getbuffer())
                tmp_path = tmp.name
            try:
                drive_link = upload_to_drive(service, attachments_folder_id, tmp_path, safe_name)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            results.append({"file_name": safe_name, "drive_link": drive_link})
        except (HttpError, OSError, DriveUploadError) as e:
            logger.error("Attachment upload failed", extra={"file": safe_name, "error": str(e)})
            st.warning(
                sanitize_for_user(
                    e,
                    default=f"Fallo subiendo {safe_name}.",
                )
            )
    return results


def _validate_form(company_name, email, tipo_solicitud, requested_by):
    """Validate form inputs. Shows st.error on failure.

    Returns:
        True if validation passed, False otherwise.
    """
    if not company_name:
        st.error("Debes ingresar el nombre de la compañía.")
        return False
    if email and not validate_emails(email):
        st.error(
            "Ingresa uno o varios correos válidos separados por coma o punto y coma."
        )
        return False
    if tipo_solicitud.lower() == "proveedor" and not requested_by:
        st.error("Debes ingresar el nombre de quien solicita (proveedor).")
        return False
    return True


def _save_request_to_db(
    session,
    profile_id,
    company_name,
    email,
    trading,
    location,
    language,
    reminder_frequency,
    tipo_solicitud,
    tipo_operacion,
    commodity,
    aduana,
    puerto,
    linea_naviera,
    requested_by,
    requested_by_type,
    tipo_aduana,
    terminales_seleccionados,
    tipo_linea,
    datos_msc,
    commercial=None,
    submitted_by_email=None,
    notes=None,
    reminder_max_months=None,
    reminder_frequency_days=None,
):
    """Persist the request and associated registrations to the database.

    The parent request, its child registrations (customs/port/shipping line)
    and the reminder schedule are written in a SINGLE transaction so a failure
    in any child rolls the whole thing back — no orphaned request flagged
    has_customs/has_port with no detail rows. The audit log is best-effort and
    committed separately so its failure never discards a saved request.

    Returns:
        request_id on success, None on failure.
    """
    with st.spinner("Guardando solicitud..."):
        try:
            # The legacy `requested_by` arg drove BOTH the requested_by string
            # AND the commercial column. Now they can diverge: an Inside Sales
            # has requested_by=IS_name but commercial=elegido. So we pass them
            # explicitly when commercial is provided, else fall back to legacy.
            request_id = insert_client_request(
                session,
                profile_id=profile_id,
                company_name=company_name,
                email=email or None,
                trading=trading,
                location=location or None,
                language=language,
                reminder_frequency=reminder_frequency,
                operation_type=(
                    tipo_operacion
                    if tipo_solicitud.lower() == "cliente"
                    else None
                ),
                commodity=(
                    commodity
                    if tipo_solicitud.lower() == "cliente"
                    else None
                ),
                has_customs=aduana,
                has_port=puerto,
                has_shipping_line=linea_naviera,
                requested_by=commercial if commercial else requested_by,
                requested_by_type=requested_by_type,
                user_email=st.session_state.get("_user_email", "unknown"),
                submitted_by_email=submitted_by_email,
                notes=notes,
                reminder_max_months=reminder_max_months,
                commit=False,
            )

            if aduana and tipo_aduana:
                insert_customs_registration(
                    session, request_id, tipo_aduana, commit=False
                )

            if puerto and terminales_seleccionados:
                insert_port_registration(
                    session, request_id, terminales_seleccionados, commit=False
                )

            if linea_naviera and tipo_linea:
                line_data = {}
                for line in tipo_linea:
                    if line == "MSC":
                        line_data[line] = datos_msc
                    else:
                        line_data[line] = {}
                insert_shipping_line_registration(
                    session, request_id, line_data, commit=False
                )

            # Reminder schedule belongs to the same atomic unit: a request must
            # never be persisted without it (otherwise reminders silently never
            # fire for that client).
            if reminder_frequency_days:
                from database.crud.reminders import insert_reminder_schedule
                insert_reminder_schedule(
                    session,
                    request_id=request_id,
                    frequency_days=reminder_frequency_days,
                    max_months=reminder_max_months,
                    commit=False,
                )

            # Single atomic commit: parent + children + reminder together.
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            session.close()
            logger.error(
                "Failed to save request to database",
                extra={"error": str(e)},
            )
            handle_error(
                e,
                sanitize_for_user(e, default="Error al guardar la solicitud."),
            )
            return None

        # Audit is best-effort and committed in its OWN transaction so its
        # failure can never roll back the request we just saved.
        _audit_email = getattr(st.user, "email", "unknown") if hasattr(st, "user") else "unknown"
        try:
            log_action(
                session=session,
                user_email=_audit_email,
                action="CREATE",
                entity_type="request",
                entity_id=request_id,
                new_value={
                    "company_name": company_name,
                    "tipo_solicitud": tipo_solicitud,
                    "trading": trading,
                    "has_customs": aduana,
                    "has_port": puerto,
                    "has_shipping_line": linea_naviera,
                },
                details=f"Request #{request_id}: {company_name}",
            )
            session.commit()
        except SQLAlchemyError:
            logger.warning("Audit log failed for request creation", exc_info=True)
            session.rollback()

        return request_id


def _save_to_sheets(
    request_id,
    tipo_solicitud,
    company_name,
    email,
    trading,
    location,
    language,
    reminder_frequency,
    requested_by,
    requested_by_type,
    tipo_operacion,
    commodity,
    aduana,
    tipo_aduana,
    puerto,
    terminales_seleccionados,
    linea_naviera,
    tipo_linea,
    datos_msc,
    case_id=None,
):
    """Sync the request to Google Sheets. Errors are logged but not fatal.

    ``case_id`` is the human-friendly identifier (e.g. ``C0042``) derived
    from the new ``requests.case_id`` column. Passed as the first column in
    the sheet; defaults to empty string when not provided.
    """
    try:
        save_request(
            {
                "request_id": request_id,
                "case_id": case_id or "",
                "tipo_solicitud": tipo_solicitud,
                "company_name": company_name,
                "email": email,
                "trading": trading,
                "location": location,
                "language": language,
                "reminder_frequency": reminder_frequency,
                "requested_by": requested_by,
                "requested_by_type": requested_by_type,
                "tipo_operacion": (
                    tipo_operacion
                    if tipo_solicitud.lower() == "cliente"
                    else None
                ),
                "commodity": (
                    commodity
                    if tipo_solicitud.lower() == "cliente"
                    else None
                ),
                "aduana": (
                    f"Sí: {', '.join(tipo_aduana)}"
                    if aduana and tipo_aduana
                    else "Sí"
                    if aduana
                    else "No"
                ),
                "puerto": (
                    "Sí: "
                    + "; ".join(
                        [
                            f"{p}: {', '.join(t)}"
                            for p, t in terminales_seleccionados.items()
                        ]
                    )
                    if puerto and terminales_seleccionados
                    else "Sí"
                    if puerto
                    else "No"
                ),
                "linea_naviera": (
                    "Sí: "
                    + ", ".join(
                        [
                            f"{linea}"
                            + (
                                f" (POL: {datos_msc.get('POL')}, "
                                f"POD: {datos_msc.get('POD')}, "
                                f"Producto: {datos_msc.get('Producto')}, "
                                f"Contenedor: {datos_msc.get('Tipo de Contenedor')}, "
                                f"Shipper BL: {datos_msc.get('Shipper en BL')})"
                                if linea == "MSC" and datos_msc
                                else ""
                            )
                            for linea in tipo_linea
                        ]
                    )
                    if linea_naviera and tipo_linea
                    else "Sí"
                    if linea_naviera
                    else "No"
                ),
            }
        )
    except (HttpError, OSError, GSpreadException, SheetsError) as e:
        logger.error(
            "Failed to save request to Google Sheets",
            extra={"request_id": request_id, "error": str(e)},
        )


def _build_email_payload(
    case_id,
    tipo_solicitud,
    company_name,
    company_info,
    requested_by,
    client_data,
    notes=None,
):
    """Assemble the dict consumed by the mailer template.

    Keys align with the snake_case ``_FIELD_MAP`` declared in
    ``services/mailer/templates.py`` so the rendered email mirrors the row
    written to Google Sheets (same column order and labels).

    ``case_id`` and ``fecha`` are included as bookkeeping — the renderer
    ignores them because they are not in ``_FIELD_MAP`` — but they keep the
    payload self-describing for debugging / future use.

    Missing or None inputs collapse to ``""`` (never ``None``) so the
    template's ``_is_empty`` check works uniformly.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    company_info = company_info or {}
    client_data = client_data or {}
    co_tz = ZoneInfo("America/Bogota")

    tipo_aduana = client_data.get("tipo_aduana") or []
    aduana_flag = client_data.get("aduana")
    if tipo_aduana:
        aduana_value = ", ".join(tipo_aduana)
    elif aduana_flag:
        aduana_value = "Sí"
    else:
        aduana_value = ""

    terminales = client_data.get("terminales_seleccionados") or {}
    puerto_flag = client_data.get("puerto")
    if terminales:
        puerto_value = ", ".join(terminales.keys())
    elif puerto_flag:
        puerto_value = "Sí"
    else:
        puerto_value = ""

    tipo_linea = client_data.get("tipo_linea") or []
    linea_flag = client_data.get("linea_naviera")
    if tipo_linea:
        linea_value = ", ".join(tipo_linea)
    elif linea_flag:
        linea_value = "Sí"
    else:
        linea_value = ""

    # MSC shipping detail: the comercial fills POL/POD/etc. and they were being
    # dropped from the email. Surface each as its own payload key so the mailer
    # template renders a labelled row (empty values collapse and are omitted).
    datos_msc = client_data.get("datos_msc") or {}

    return {
        "case_id": case_id or "",
        "fecha": datetime.now(co_tz).strftime("%Y-%m-%d %H:%M:%S"),
        "requested_by": requested_by or "",
        "tipo_solicitud": tipo_solicitud or "",
        "company_name": company_name or "",
        "email": company_info.get("email") or "",
        "trading": company_info.get("trading") or "",
        "location": company_info.get("location") or "",
        "language": company_info.get("language") or "",
        "reminder_frequency": company_info.get("reminder_frequency") or "",
        "tipo_operacion": client_data.get("tipo_operacion") or "",
        "commodity": client_data.get("commodity") or "",
        "aduana": aduana_value,
        "puerto": puerto_value,
        "linea_naviera": linea_value,
        "pol": datos_msc.get("POL") or "",
        "pod": datos_msc.get("POD") or "",
        "producto": datos_msc.get("Producto") or "",
        "tipo_contenedor": datos_msc.get("Tipo de Contenedor") or "",
        "shipper_bl": datos_msc.get("Shipper en BL") or "",
        "notes": notes or "",
    }


def _get_current_user(session):
    """Build a current_user dict from session_state, augmenting with users table.

    Falls back to a synthesized minimal dict if the email is not in users
    (e.g. a brand new user before being added by an admin).
    """
    from services.users import get_user
    email = st.session_state.get("_user_email")
    rol = st.session_state.get("_user_role", "otro")
    user = get_user(session, email) if email else None
    if not user:
        display = st.session_state.get("_user_display_name") or email or "Usuario"
        user = {"email": email or "unknown", "nombre_display": display, "rol": rol, "activo": True}
    return user


def forms():
    """Main request form entry point.

    Renders the complete request creation form and handles submission.
    """
    session = SessionLocal()
    try:
        render_section_header("1. Tipo de Solicitud")
        tipo_solicitud, profile_id = _render_request_type_selector(session)
        if tipo_solicitud is None:
            return

        current_user = _get_current_user(session)
        requester = _render_requester_section(session, tipo_solicitud, current_user)
        # Backward-compat: keep these locals so the rest of the function works.
        requested_by = requester.get("requested_by")
        requested_by_type = requester.get("requested_by_type")
        commercial_for_request = requester.get("commercial")
        submitted_by_email = requester.get("submitted_by_email")
        render_section_header("2. Datos de la Compania")
        company_info = _render_company_info()

        # Client-specific fields
        client_data = {}
        if tipo_solicitud.lower() == "cliente":
            render_section_header("3. Operacion y Registros")
            client_data = _render_client_specifics()
        else:
            st.selectbox(
                "Tipo de Proveedor", PROVIDER_TYPES, key="tipo_proveedor"
            )

        # Phase 4: notes + attachments (optional, both flows)
        render_section_header("4. Notas y Adjuntos")
        notes, attachment_files = _render_notes_and_attachments()

        # -------- Save button (no st.form) --------
        if st.button("Guardar", key="guardar_general"):
            # Re-validate the requester payload at submission time
            if not requester.get("valid", True):
                st.error(requester.get("error", "Datos del solicitante inválidos."))
                return

            company_name = sanitize_company_name(company_info["company_name"])

            if not _validate_form(
                company_name,
                company_info["email"],
                tipo_solicitud,
                requested_by,
            ):
                return

            # Canonicalize one-or-many client emails once, so the DB, Google
            # Sheets and the compliance email all store the same trimmed value.
            company_info["email"] = normalize_emails(company_info["email"])

            request_id = _save_request_to_db(
                session=session,
                profile_id=profile_id,
                company_name=company_name,
                email=company_info["email"],
                trading=company_info["trading"],
                location=company_info["location"],
                language=company_info["language"],
                reminder_frequency=company_info["reminder_frequency"],
                tipo_solicitud=tipo_solicitud,
                tipo_operacion=client_data.get("tipo_operacion"),
                commodity=client_data.get("commodity"),
                aduana=client_data.get("aduana", False),
                puerto=client_data.get("puerto", False),
                linea_naviera=client_data.get("linea_naviera", False),
                requested_by=requested_by,
                requested_by_type=requested_by_type,
                tipo_aduana=client_data.get("tipo_aduana", []),
                terminales_seleccionados=client_data.get(
                    "terminales_seleccionados", {}
                ),
                tipo_linea=client_data.get("tipo_linea", []),
                datos_msc=client_data.get("datos_msc", {}),
                commercial=commercial_for_request,
                submitted_by_email=submitted_by_email,
                notes=notes or None,
                reminder_max_months=company_info.get("reminder_max_months"),
                reminder_frequency_days=company_info.get("reminder_frequency_days"),
            )
            if request_id is None:
                return

            # Reminder schedule is now created inside _save_request_to_db, in the
            # same atomic transaction as the request itself.

            # Show case_id as proof of submission
            from database.crud.clientes import get_case_id
            _case_id = get_case_id(session, request_id)
            if _case_id:
                st.toast(f"Solicitud creada. Case ID: {_case_id}", icon=":material/task_alt:")

            # Phase 4: upload attachments (best-effort, errors per-file)
            if attachment_files:
                try:
                    from services.google_drive_utils import init_drive
                    from database.crud.request_attachments import insert_request_attachment
                    drive_service = init_drive()
                    base_folder_key = (
                        "clients_folder_id" if tipo_solicitud.lower() == "cliente"
                        else "providers_folder_id"
                    )
                    base_folder_id = st.secrets["drive"][base_folder_key]
                    uploaded_by = st.session_state.get("_user_email", "unknown")
                    upload_results = _upload_attachments_to_drive(
                        drive_service,
                        base_folder_id=base_folder_id,
                        entity_type=tipo_solicitud.lower(),
                        company_name=company_name,
                        files=attachment_files,
                        uploaded_by=uploaded_by,
                    )
                    for r in upload_results:
                        insert_request_attachment(
                            session,
                            request_id=request_id,
                            file_name=r["file_name"],
                            drive_link=r["drive_link"],
                            uploaded_by=uploaded_by,
                        )
                        try:
                            log_action(
                                session=session,
                                user_email=uploaded_by,
                                action="UPLOAD",
                                entity_type="request_attachment",
                                entity_id=request_id,
                                details=f"{r['file_name']}",
                            )
                            session.commit()
                        except SQLAlchemyError:
                            logger.warning("Audit log failed for attachment", exc_info=True)
                    if upload_results:
                        st.success(f"Se subieron {len(upload_results)} adjunto(s) a Drive.")
                except (HttpError, OSError, DriveUploadError, SQLAlchemyError, KeyError) as e:
                    logger.error("Attachment flow failed", extra={"error": str(e)})
                    st.warning(
                        sanitize_for_user(e, default="Adjuntos no procesados.")
                    )

            if _is_sheets_enabled():
                _save_to_sheets(
                    request_id=request_id,
                    tipo_solicitud=tipo_solicitud,
                    company_name=company_name,
                    email=company_info["email"],
                    trading=company_info["trading"],
                    location=company_info["location"],
                    language=company_info["language"],
                    reminder_frequency=company_info["reminder_frequency"],
                    requested_by=requested_by,
                    requested_by_type=requested_by_type,
                    tipo_operacion=client_data.get("tipo_operacion"),
                    commodity=client_data.get("commodity"),
                    aduana=client_data.get("aduana", False),
                    tipo_aduana=client_data.get("tipo_aduana", []),
                    puerto=client_data.get("puerto", False),
                    terminales_seleccionados=client_data.get(
                        "terminales_seleccionados", {}
                    ),
                    linea_naviera=client_data.get("linea_naviera", False),
                    tipo_linea=client_data.get("tipo_linea", []),
                    datos_msc=client_data.get("datos_msc", {}),
                    case_id=_case_id,
                )
            else:
                logger.info(
                    "Google Sheets sync disabled (st.secrets['sheets']['enabled'] falsy)",
                    extra={"case_id": _case_id, "request_id": request_id},
                )

            # Phase 8: send compliance notification email (best-effort).
            # Local import keeps the hot path clean and avoids pulling SMTP
            # code into modules that never submit a form. NOTE: when
            # st.secrets["mailer"]["enabled"] is True in production, the
            # Apps Script notifier attached to the Google Sheet must be
            # disabled to avoid duplicate emails to compliance.
            try:
                from services.mailer import send_request_notification
                _payload = _build_email_payload(
                    case_id=_case_id,
                    tipo_solicitud=tipo_solicitud,
                    company_name=company_name,
                    company_info=company_info,
                    requested_by=requested_by,
                    client_data=client_data,
                    notes=notes,
                )
                _creator_email = st.session_state.get("_user_email") or submitted_by_email
                send_request_notification(
                    session=session,
                    case_id=_case_id,
                    payload=_payload,
                    creator_email=_creator_email,
                    submitted_by_email=submitted_by_email,
                )
            except MailerError as e:
                logger.error("Mailer failed for case %s", _case_id, exc_info=True)
                st.warning(sanitize_for_user(e))
            except Exception:  # intentional-broad: defensive — the request
                # has already been persisted successfully at this point; we
                # must never surface an unexpected error from the notification
                # path that would make the user think saving failed.
                logger.exception("Unexpected mailer error for case %s", _case_id)
                st.warning(
                    "Solicitud guardada. Hubo un problema notificando a compliance por correo."
                )

            session.close()
            st.success("Solicitud guardada correctamente")
    finally:
        # session.close() is best-effort cleanup in the finally path: we do not
        # want a secondary failure during teardown (e.g. a stale/broken pool
        # connection) to mask the original exception or crash the page. A
        # broad except is intentional here.
        try:
            session.close()
        except Exception:  # noqa: BLE001 - intentional best-effort teardown
            pass
