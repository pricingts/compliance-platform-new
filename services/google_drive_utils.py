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

def find_or_create_folder(service, folder_name: str, *, shared_drive_id: str | None = None, parent_folder_id: str | None = None) -> str:
    """
    Si parent_folder_id está definido: trabaja dentro de esa carpeta.
    Si no, usa shared_drive_id para trabajar en la raíz de la unidad compartida.
    """
    try:
        if parent_folder_id:
            # Buscar dentro de una carpeta específica (carpeta padre)
            query = (
                f"name = '{folder_name}' and "
                f"mimeType = 'application/vnd.google-apps.folder' and "
                f"trashed = false and "
                f"'{parent_folder_id}' in parents"
            )
            res = service.files().list(
                q=query,
                corpora="allDrives",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields="files(id, name)",
                pageSize=10,
            ).execute()
            files = res.get("files", [])
            if files:
                return files[0]["id"]

            metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_folder_id],
            }
            folder = service.files().create(
                body=metadata,
                supportsAllDrives=True,
                fields="id"
            ).execute()
            return folder["id"]

        if shared_drive_id:
            # Buscar en la raíz de la unidad compartida
            query = (
                f"name = '{folder_name}' and "
                f"mimeType = 'application/vnd.google-apps.folder' and "
                f"trashed = false"
            )
            res = service.files().list(
                q=query,
                corpora="drive",
                driveId=shared_drive_id,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields="files(id, name)",
                pageSize=10,
            ).execute()
            files = res.get("files", [])
            if files:
                return files[0]["id"]

            metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [shared_drive_id],  # raíz de la unidad
            }
            folder = service.files().create(
                body=metadata,
                supportsAllDrives=True,
                fields="id"
            ).execute()
            return folder["id"]

        raise ValueError("Debes proporcionar shared_drive_id o parent_folder_id.")

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
