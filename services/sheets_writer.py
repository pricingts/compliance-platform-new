"""Google Sheets writer for request metadata (sheet: ``Solicitudes de Creacion``).

Phase 5 hardening:
- ``@with_retry`` on I/O paths for ``HttpError`` / ``OSError`` /
  ``APIError`` / ``ConnectionError``.
- gspread client is configured with a 30-second request timeout via
  ``Client.set_timeout``.
- ``SpreadsheetNotFound`` raises :class:`~utils.exceptions.SheetsError`
  instead of calling ``st.error`` — the UI layer decides how to surface
  failures.
- Creation of a missing worksheet logs a structured warning instead of
  rendering ``st.warning``; UI presentation belongs to ``forms/*``.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.errors import HttpError

from services.logging_config import get_logger
from utils.exceptions import SheetsError
from utils.retry import with_retry

CO_TZ = ZoneInfo("America/Bogota")

# 30s transport timeout applied to the gspread client on initialisation.
_GSPREAD_TIMEOUT_SECONDS = 30

_client: gspread.Client | None = None
_sheets_service = None
_compliance_id: str | None = None

_RETRYABLE_SHEETS_EXCEPTIONS = (
    HttpError,
    OSError,
    ConnectionError,
    gspread.exceptions.APIError,
)

logger = get_logger(__name__)


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
    # Enforce a network-level timeout so a hung request can't block the
    # Streamlit run indefinitely. gspread exposes this on Client since
    # 6.0; guarded defensively in case the attribute ever moves.
    try:
        _client.set_timeout(_GSPREAD_TIMEOUT_SECONDS)
    except AttributeError:  # pragma: no cover — safety net for older gspread
        logger.warning(
            "gspread.Client has no set_timeout; skipping request timeout"
        )
    _sheets_service = build("sheets", "v4", credentials=credentials)
    _compliance_id = st.secrets["general"]["compliance_id"]


@with_retry(
    max_attempts=3,
    backoff=1.5,
    exceptions=_RETRYABLE_SHEETS_EXCEPTIONS,
    jitter=True,
)
def get_or_create_worksheet(sheet_name: str, headers: list | None = None):
    """Return the worksheet, creating it on first use.

    Raises:
        SheetsError: When the configured spreadsheet ID is unknown (wrong
            ``compliance_id``) or the worksheet cannot be opened.
    """
    _init()
    try:
        sheet = _client.open_by_key(_compliance_id)
    except gspread.exceptions.SpreadsheetNotFound as e:
        logger.error(
            "Spreadsheet not found",
            extra={"compliance_id": _compliance_id},
        )
        raise SheetsError("No se encontró la hoja de cálculo.") from e

    try:
        worksheet = sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=sheet_name, rows="1000", cols="30")
        if headers:
            worksheet.append_row(headers)
        logger.warning(
            "Created missing worksheet",
            extra={"sheet_name": sheet_name},
        )
    return worksheet


@with_retry(
    max_attempts=3,
    backoff=1.5,
    exceptions=_RETRYABLE_SHEETS_EXCEPTIONS,
    jitter=True,
)
def _append_row_with_retry(worksheet, row, value_input_option: str = "USER_ENTERED"):
    """Retry-wrapped ``worksheet.append_row`` call.

    Isolated so that ``save_request``'s retry budget doesn't compound with
    ``get_or_create_worksheet``'s (each gets their own 3-attempt budget).
    """
    worksheet.append_row(row, value_input_option=value_input_option)


def save_request(request_info: dict):
    """Append a request summary row to ``Solicitudes de Creacion``.

    Raises:
        SheetsError: Propagated from :func:`get_or_create_worksheet`.
        gspread.exceptions.APIError / HttpError / OSError: Transient
            failures are retried; persistent ones re-raise after the
            retry budget is exhausted so the caller can log + degrade.
    """
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
        # Defensive: get_or_create_worksheet now raises on failure instead
        # of returning None, but we keep this guard so an unexpected None
        # does not blow up with an AttributeError deeper in the call stack.
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

    _append_row_with_retry(ws, row, value_input_option="USER_ENTERED")
