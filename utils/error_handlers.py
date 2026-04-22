"""Error handling utilities for Streamlit UI."""
import streamlit as st

from services.logging_config import get_logger
from utils.exceptions import (
    AuthenticationError,
    ComplianceError,
    DatabaseError,
    DriveUploadError,
    MailerError,
    ValidationError,
)

logger = get_logger(__name__)


def handle_error(error: Exception, user_message: str = None):
    """Log the error and display a user-friendly message in Streamlit.

    Args:
        error: The exception that occurred.
        user_message: Optional message to display to the user. If not
            provided, a generic Spanish-language message is shown.
    """
    logger.error(
        f"{type(error).__name__}: {error}",
        extra={"error_type": type(error).__name__},
    )

    display_message = user_message or "Ha ocurrido un error. Por favor, intenta de nuevo."
    st.error(f"Error: {display_message}")


def sanitize_for_user(
    exc: Exception,
    default: str = "Ocurrió un error inesperado.",
) -> str:
    """Return a user-safe message for ``exc``, never exposing stack traces or
    internal class names.

    Mapping:
      * ValidationError       -> the exception's own message (already UX-safe).
      * DatabaseError         -> generic DB failure message.
      * DriveUploadError      -> generic Drive upload failure message.
      * AuthenticationError   -> generic auth failure message.
      * MailerError           -> generic mailer failure message.
      * ComplianceError base  -> ``default``.
      * Anything else         -> ``default``.
    """
    if isinstance(exc, ValidationError):
        return str(exc)
    if isinstance(exc, DatabaseError):
        return "No se pudo completar la operación en la base de datos. Inténtalo de nuevo."
    if isinstance(exc, DriveUploadError):
        return "No se pudo subir el archivo a Drive. Verifica permisos e inténtalo de nuevo."
    if isinstance(exc, AuthenticationError):
        return "Problema de autenticación. Inicia sesión nuevamente."
    if isinstance(exc, MailerError):
        return "No se pudo enviar la notificación por correo. El administrador será avisado."
    if isinstance(exc, ComplianceError):
        return default
    return default
