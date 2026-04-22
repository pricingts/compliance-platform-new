# services/google_drive_utils.py

"""Google Drive helpers (service initialisation, folder management, upload).

Phase 5 hardening:
- I/O functions decorated with ``@with_retry`` for ``HttpError``,
  ``OSError``, ``TimeoutError``, ``ConnectionError``.
- Authentication failures (``RefreshError``) bypass the retry because
  retrying a bad token never succeeds — they propagate immediately.
- After all retries are exhausted, terminal ``HttpError`` is re-raised as
  ``DriveUploadError`` so UI callers can use ``sanitize_for_user`` uniformly.
- Transport timeout: ``MediaFileUpload`` uses ``resumable=True`` (chunked
  upload with built-in backoff). Passing a custom ``httplib2.Http(timeout=...)``
  into ``build()`` requires threading a credentialed ``AuthorizedHttp``
  instance through the service object, which is invasive. We defer that
  to a future pass and rely on the resumable-upload behaviour plus the
  retry decorator for now.
  TODO(phase-6): evaluate ``google_auth_httplib2.AuthorizedHttp`` +
  ``httplib2.Http(timeout=30)`` wiring to enforce a hard transport timeout.
"""

import mimetypes
from typing import Optional

import streamlit as st
from google.auth.exceptions import RefreshError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from services.logging_config import get_logger
from utils.exceptions import DriveUploadError
from utils.retry import with_retry

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

# Exception classes that justify a retry. ``RefreshError`` is intentionally
# excluded — a bad credential never becomes valid by trying again.
_RETRYABLE_DRIVE_EXCEPTIONS = (HttpError, OSError, TimeoutError, ConnectionError)

logger = get_logger(__name__)


def init_drive():
    """Build an authenticated Drive v3 service client.

    Not decorated with retry because failure here is almost always a
    credential problem; the caller should surface it directly.
    """
    sa_info = dict(st.secrets["google_drive_credentials"])
    credentials = service_account.Credentials.from_service_account_info(
        sa_info, scopes=DRIVE_SCOPES
    )
    service = build("drive", "v3", credentials=credentials)
    return service


@with_retry(
    max_attempts=3,
    backoff=1.5,
    exceptions=_RETRYABLE_DRIVE_EXCEPTIONS,
    jitter=True,
)
def _find_or_create_folder_raw(
    service,
    folder_name: str,
    *,
    entity_type: str,
    base_folder_id: str,
) -> str:
    """Retryable body of :func:`find_or_create_folder`.

    Raises the underlying ``HttpError`` / ``OSError`` / etc. so the retry
    decorator can see them. Mapping to ``DriveUploadError`` happens in
    the public wrapper after retries are exhausted.
    """
    folder_name = folder_name.strip()

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
        return existing_folders[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [base_folder_id],
    }

    folder = service.files().create(
        body=metadata,
        supportsAllDrives=True,
        fields="id",
    ).execute()

    return folder["id"]


def find_or_create_folder(
    service,
    folder_name: str,
    *,
    entity_type: str,  # "cliente" o "proveedor"
    base_folder_id: str,
) -> str:
    """Find or create a folder inside the CLIENTE / PROVEEDOR base folder.

    Estructura esperada:
      base_folder_id/
        {NombreCliente}/
      o
      base_folder_id/
        {NombreProveedor}/
    """
    try:
        return _find_or_create_folder_raw(
            service,
            folder_name,
            entity_type=entity_type,
            base_folder_id=base_folder_id,
        )
    except RefreshError:
        # Credential rot — propagate verbatim so the auth boundary can react.
        raise
    except HttpError as e:
        raise DriveUploadError(
            f"Error buscando/creando carpeta en Drive: {e}"
        ) from e


@with_retry(
    max_attempts=3,
    backoff=1.5,
    exceptions=_RETRYABLE_DRIVE_EXCEPTIONS,
    jitter=True,
)
def _find_or_create_subfolder_raw(
    service, parent_folder_id: str, subfolder_name: str
) -> str:
    """Retryable body of :func:`find_or_create_subfolder`."""
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


def find_or_create_subfolder(
    service, parent_folder_id: str, subfolder_name: str
) -> str:
    """Find or create a subfolder inside a given parent folder.

    Use case: under ``{company_name}/`` create ``Adjuntos Solicitud/`` for
    the request's free-form attachments (Phase 4 / F4).
    """
    try:
        return _find_or_create_subfolder_raw(service, parent_folder_id, subfolder_name)
    except RefreshError:
        raise
    except HttpError as e:
        raise DriveUploadError(
            f"Error buscando/creando subcarpeta en Drive: {e}"
        ) from e


@with_retry(
    max_attempts=3,
    backoff=1.5,
    exceptions=_RETRYABLE_DRIVE_EXCEPTIONS,
    jitter=True,
)
def _upload_to_drive_raw(
    service,
    folder_id: str,
    file_path: str,
    file_name: str,
    mimetype: Optional[str] = None,
) -> str:
    """Retryable body of :func:`upload_to_drive`.

    Each retry rebuilds ``MediaFileUpload`` because its internal cursor is
    not guaranteed to be re-usable across failures.
    """
    if mimetype is None:
        guessed, _ = mimetypes.guess_type(file_name)
        mimetype = guessed or "application/octet-stream"

    media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
    metadata = {"name": file_name, "parents": [folder_id]}
    file = service.files().create(
        body=metadata,
        media_body=media,
        supportsAllDrives=True,
        fields="id, webViewLink",
    ).execute()

    file_id = file["id"]

    # Documents inherit permissions from the shared drive folder.
    # No public "anyone" permission is created (security fix).

    return file.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"


def upload_to_drive(
    service,
    folder_id: str,
    file_path: str,
    file_name: str,
    mimetype: Optional[str] = None,
) -> str:
    """Upload a file to Drive. Auto-detects mimetype from filename when not provided.

    Phase 4 fix: previously hardcoded ``application/pdf``, which corrupted
    DOCX/XLSX/PNG uploads. Now auto-detects via ``mimetypes.guess_type()``,
    falling back to ``application/octet-stream`` for unknown types.

    Phase 5: retry on transient HTTP / OS errors; map terminal failure to
    ``DriveUploadError``; never retry on ``RefreshError``.
    """
    try:
        return _upload_to_drive_raw(service, folder_id, file_path, file_name, mimetype)
    except RefreshError:
        raise
    except HttpError as e:
        raise DriveUploadError(
            f"Error subiendo archivo a Drive: {e}",
            file_name=file_name,
        ) from e
