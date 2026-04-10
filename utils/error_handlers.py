"""Error handling utilities for Streamlit UI."""
import streamlit as st

from services.logging_config import get_logger

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
