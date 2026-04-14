# services/google_drive_utils.py

import mimetypes
from typing import Optional

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

def init_drive():
    sa_info = dict(st.secrets['google_drive_credentials'])
    credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=DRIVE_SCOPES)
    service = build("drive", "v3", credentials=credentials)
    return service


def find_or_create_folder(
    service,
    folder_name: str,
    *,
    entity_type: str,  # "cliente" o "proveedor"
    base_folder_id: str,  # ID de la carpeta CLIENTE o PROVEEDOR
) -> str:
    """
    Busca o crea una carpeta dentro de la carpeta base (CLIENTE o PROVEEDOR) en Google Drive.

    Estructura esperada:
      base_folder_id/
        {NombreCliente}/
      o
      base_folder_id/
        {NombreProveedor}/
    """

    try:
        # 1️⃣ Normaliza el nombre de la carpeta
        folder_name = folder_name.strip()

        # 2️⃣ Buscar la subcarpeta dentro de la carpeta base
        query = (
            f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and trashed = false and '{base_folder_id}' in parents"
        )

        res = service.files().list(
            q=query,
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="files(id, name)",
            pageSize=5,
        ).execute()

        existing_folders = res.get("files", [])
        if existing_folders:
            # ✅ Ya existe la carpeta del cliente/proveedor
            return existing_folders[0]["id"]

        # 3️⃣ Crear la carpeta si no existe
        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [base_folder_id],
        }

        folder = service.files().create(
            body=metadata,
            supportsAllDrives=True,
            fields="id"
        ).execute()

        return folder["id"]

    except HttpError as e:
        raise RuntimeError(f"Error buscando/creando carpeta en Drive: {e}")


def find_or_create_subfolder(service, parent_folder_id: str, subfolder_name: str) -> str:
    """Find or create a subfolder inside a given parent folder.

    Use case: under {company_name}/, create 'Adjuntos Solicitud/' for the
    request's free-form attachments (Phase 4 / F4).
    """
    try:
        subfolder_name = subfolder_name.strip()
        query = (
            f"name = '{subfolder_name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and trashed = false and '{parent_folder_id}' in parents"
        )
        res = service.files().list(
            q=query,
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="files(id, name)",
            pageSize=5,
        ).execute()
        existing = res.get("files", [])
        if existing:
            return existing[0]["id"]

        metadata = {
            "name": subfolder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_folder_id],
        }
        folder = service.files().create(
            body=metadata,
            supportsAllDrives=True,
            fields="id",
        ).execute()
        return folder["id"]
    except HttpError as e:
        raise RuntimeError(f"Error buscando/creando subcarpeta en Drive: {e}")


def upload_to_drive(
    service,
    folder_id: str,
    file_path: str,
    file_name: str,
    mimetype: Optional[str] = None,
) -> str:
    """Upload a file to Drive. Auto-detects mimetype from filename when not provided.

    Phase 4 fix: previously hardcoded `application/pdf`, which corrupted
    DOCX/XLSX/PNG uploads. Now auto-detects via `mimetypes.guess_type()`,
    falling back to `application/octet-stream` for unknown types.
    """
    try:
        if mimetype is None:
            guessed, _ = mimetypes.guess_type(file_name)
            mimetype = guessed or "application/octet-stream"

        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
        metadata = {"name": file_name, "parents": [folder_id]}
        file = service.files().create(
            body=metadata,
            media_body=media,
            supportsAllDrives=True,
            fields="id, webViewLink"
        ).execute()

        file_id = file["id"]

        # Documents inherit permissions from the shared drive folder.
        # No public "anyone" permission is created (security fix).

        return file.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

    except HttpError as e:
        raise RuntimeError(f"Error subiendo archivo a Drive: {e}")
