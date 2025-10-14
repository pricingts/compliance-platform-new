# services/google_drive_utils.py

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

from googleapiclient.errors import HttpError

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


def upload_to_drive(service, folder_id: str, file_path: str, file_name: str) -> str:
    try:
        media = MediaFileUpload(file_path, mimetype="application/pdf", resumable=True)
        metadata = {"name": file_name, "parents": [folder_id]}
        file = service.files().create(
            body=metadata,
            media_body=media,
            supportsAllDrives=True,
            fields="id, webViewLink"
        ).execute()

        file_id = file["id"]

        # Dar permiso de lectura por enlace
        try:
            service.permissions().create(
                fileId=file_id,
                supportsAllDrives=True,
                body={"type": "anyone", "role": "reader"},
            ).execute()
        except HttpError:
            pass

        return file.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

    except HttpError as e:
        raise RuntimeError(f"Error subiendo archivo a Drive: {e}")
