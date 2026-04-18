import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from zoneinfo import ZoneInfo

CO_TZ = ZoneInfo("America/Bogota")

_client = None
_sheets_service = None
_compliance_id = None


def _init():
    """Lazy initialization of Google credentials and clients.

    Called automatically by public functions on first use.  This avoids
    crashing at module import time when secrets are not available (e.g.
    during testing or CI).
    """
    global _client, _sheets_service, _compliance_id
    if _client is not None:
        return

    import streamlit as st
    from googleapiclient.discovery import build

    credentials = Credentials.from_service_account_info(
        st.secrets["google_sheets_credentials"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    _client = gspread.authorize(credentials)
    _sheets_service = build("sheets", "v4", credentials=credentials)
    _compliance_id = st.secrets["general"]["compliance_id"]


def get_or_create_worksheet(sheet_name: str, headers: list = None):
    _init()
    try:
        sheet = _client.open_by_key(_compliance_id)
        try:
            worksheet = sheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            import streamlit as st
            worksheet = sheet.add_worksheet(title=sheet_name, rows="1000", cols="30")
            if headers:
                worksheet.append_row(headers)
            st.warning(f"Worksheet '{sheet_name}' was created.")
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        import streamlit as st
        st.error("No se encontró la hoja de cálculo.")
        return None


def save_request(request_info: dict):
    _init()

    headers = [
        "Case ID",
        "Fecha",
        "Solicitante",
        "Tipo de solicitud",
        "Nombre Compañía",
        "Correo",
        "Cuenta Trading",
        "País / Ubicación",
        "Idioma",
        "Frecuencia Recordatorio",
        "Tipo de Operación",
        "Commodity",
        "Aduana",
        "Puerto",
        "Línea Naviera",
    ]

    ws = get_or_create_worksheet("Solicitudes de Creacion", headers)
    if not ws:
        return

    fecha_creacion = datetime.now(CO_TZ).strftime("%Y-%m-%d %H:%M:%S")

    row = [
        request_info.get("case_id", ""),
        fecha_creacion,
        request_info.get("requested_by", ""),
        request_info.get("tipo_solicitud", ""),
        request_info.get("company_name", ""),
        request_info.get("email", ""),
        request_info.get("trading", ""),
        request_info.get("location", ""),
        request_info.get("language", ""),
        request_info.get("reminder_frequency", ""),
        request_info.get("tipo_operacion", ""),
        request_info.get("commodity", ""),
        request_info.get("aduana", ""),
        request_info.get("puerto", ""),
        request_info.get("linea_naviera", ""),
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")
