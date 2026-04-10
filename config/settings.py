# config/settings.py
import os
from typing import Set


def _get_secret(key: str, default: str = "") -> str:
    """Get a config value from Streamlit secrets or environment variables."""
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return os.getenv(key, default)


def get_admin_emails() -> Set[str]:
    """Get the set of admin emails from configuration."""
    raw = _get_secret("ADMIN_EMAILS", "")
    if raw:
        return {e.strip().lower() for e in raw.split(",") if e.strip()}

    # Fallback: build from usernames and domains
    usernames_raw = _get_secret(
        "ADMIN_USERNAMES",
        "compliance,compliance1,compliance2,sjaafar,jsanchez,pricing5",
    )
    domains_raw = _get_secret(
        "ADMIN_DOMAINS",
        "@tradingsolutions.com,@tradingsol.com",
    )

    usernames = {u.strip() for u in usernames_raw.split(",") if u.strip()}
    domains = {d.strip() for d in domains_raw.split(",") if d.strip()}

    return {u + d for u in usernames for d in domains}


def get_session_timeout_minutes() -> int:
    """Get session timeout in minutes."""
    raw = _get_secret("SESSION_TIMEOUT_MINUTES", "480")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 480


def get_env() -> str:
    """Get current environment (dev/staging/production)."""
    return os.getenv("ENV", "dev")
