import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
from googleapiclient.discovery import build
from datetime import datetime
import pytz

credentials = Credentials.from_service_account_info(
    st.secrets["google_sheets_credentials"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
)

client_gcp = gspread.authorize(credentials)
sheets_service = build("sheets", "v4", credentials=credentials)
COMPLIANCE_ID = st.secrets["general"]["compliance_id"]
colombia_timezone = pytz.timezone('America/Bogota')

def get_or_create_worksheet(sheet_name: str, headers: list = None):
    try:
        sheet = client_gcp.open_by_key(COMPLIANCE_ID)
        try:
            worksheet = sheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=sheet_name, rows="1000", cols="30")
            if headers:
                worksheet.append_row(headers)
            st.warning(f"Worksheet '{sheet_name}' was created.")
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("No se encontró la hoja de cálculo.")
        return None

def save_request(request_info: dict):

    headers = ["Fecha", "Solicitante", "Tipo de perfil", "Nombre Compañia", "Nombre Completo", "Cedula", "Correo", "Cuenta Trading", "Direccion", "Idioma", "Frecuencia Recordatorio"]

    ws = get_or_create_worksheet("Solicitudes de Creacion", headers)

    if not ws:
        return

    colombia_timezone = pytz.timezone("America/Bogota")
    fecha_creacion = datetime.now(pytz.utc).astimezone(colombia_timezone).strftime("%Y-%m-%d %H:%M:%S")

    row = [
        fecha_creacion,
        request_info.get("requested_by", ""),
        request_info.get("tipo_solicitud", ""),
        request_info.get("company_name", ""),
        request_info.get("nombre_completo", ""),
        request_info.get("cedula", ""),
        request_info.get("email", ""),
        request_info.get("trading", ""),
        request_info.get("location", ""),
        request_info.get("language", ""),
        request_info.get("reminder_frequency", ""),

    ]
    ws.append_row(row, value_input_option="USER_ENTERED")