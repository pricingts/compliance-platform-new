import streamlit as st
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
from utils.error_handlers import handle_error
from utils.ui_helpers import render_section_header
from utils.validators import validate_email, sanitize_company_name
from config.constants import (
    COMERCIALES,
    TERMINALES,
    TRADING_COUNTRIES,
    REMINDER_FREQUENCIES,
    OPERATION_TYPES,
    CUSTOMS_SYSTEMS,
    SHIPPING_LINES,
    PORTS,
    MSC_CONTAINER_TYPES,
    LANGUAGES,
    PROVIDER_TYPES,
)

logger = get_logger(__name__)


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
    except Exception as e:
        session.close()
        handle_error(e, "Error al conectar con la base de datos.")
        return None, None

    if not profile_id:
        session.close()
        st.error("El perfil seleccionado no existe en la base de datos.")
        return None, None

    return tipo_solicitud, profile_id


def _render_requester_section(tipo_solicitud):
    """Render the requester input depending on request type.

    Returns:
        tuple: (requested_by, requested_by_type)
    """
    requested_by = None
    requested_by_type = None

    if tipo_solicitud.lower() == "cliente":
        requested_by = st.selectbox("Comercial", COMERCIALES, key="comercial")
        requested_by_type = "comercial"
    elif tipo_solicitud.lower() == "proveedor":
        requested_by = st.text_input(
            "Nombre de quien solicita", key="solicitante_proveedor"
        )
        requested_by_type = "solicitante_proveedor"

    return requested_by, requested_by_type


def _render_company_info():
    """Render the 3-column layout with company fields.

    Returns:
        dict with keys: company_name, language, trading, email, location,
              reminder_frequency.
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
        email = st.text_input("Correo electrónico", key="correo_compania")
    with col3:
        location = st.text_input(
            "Pais de la Compañía a Registrar", key="ubicacion_compania"
        )
        reminder_frequency = st.selectbox(
            "Frecuencia de recordatorio",
            REMINDER_FREQUENCIES,
            key="frecuencia_recordatorio",
        )

    return {
        "company_name": company_name,
        "language": language,
        "trading": trading,
        "email": email,
        "location": location,
        "reminder_frequency": reminder_frequency,
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


def _validate_form(company_name, email, tipo_solicitud, requested_by):
    """Validate form inputs. Shows st.error on failure.

    Returns:
        True if validation passed, False otherwise.
    """
    if not company_name:
        st.error("Debes ingresar el nombre de la compañía.")
        return False
    if email and not validate_email(email):
        st.error("El correo electrónico no parece válido.")
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
):
    """Persist the request and associated registrations to the database.

    Returns:
        request_id on success, None on failure.
    """
    with st.spinner("Guardando solicitud..."):
        try:
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
                requested_by=requested_by,
                requested_by_type=requested_by_type,
                user_email=st.session_state.get("_user_email", "unknown"),
            )

            if aduana and tipo_aduana:
                insert_customs_registration(session, request_id, tipo_aduana)

            if puerto and terminales_seleccionados:
                insert_port_registration(
                    session, request_id, terminales_seleccionados
                )

            if linea_naviera and tipo_linea:
                line_data = {}
                for line in tipo_linea:
                    if line == "MSC":
                        line_data[line] = datos_msc
                    else:
                        line_data[line] = {}
                insert_shipping_line_registration(
                    session, request_id, line_data
                )

            # Audit: log request creation
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
            except Exception:
                logger.warning("Audit log failed for request creation", exc_info=True)

            return request_id
        except Exception as e:
            session.rollback()
            session.close()
            logger.error(
                "Failed to save request to database",
                extra={"error": str(e)},
            )
            handle_error(e, f"Error al guardar la solicitud: {e}")
            return None


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
):
    """Sync the request to Google Sheets. Errors are logged but not fatal."""
    try:
        save_request(
            {
                "request_id": request_id,
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
    except Exception as e:
        logger.error(
            "Failed to save request to Google Sheets",
            extra={"request_id": request_id, "error": str(e)},
        )


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

        requested_by, requested_by_type = _render_requester_section(
            tipo_solicitud
        )
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

        # -------- Save button (no st.form) --------
        if st.button("Guardar", key="guardar_general"):
            company_name = sanitize_company_name(company_info["company_name"])

            if not _validate_form(
                company_name,
                company_info["email"],
                tipo_solicitud,
                requested_by,
            ):
                return

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
            )
            if request_id is None:
                return

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
            )

            session.close()
            st.success("Solicitud guardada correctamente")
    finally:
        try:
            session.close()
        except Exception:
            pass
