"""UI helper functions for the compliance platform theme."""
from __future__ import annotations

from pathlib import Path

import streamlit as st


def load_css() -> None:
    """Inject the global CSS stylesheet into the Streamlit page."""
    css_path = Path(__file__).parent.parent / "assets" / "styles.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


_STATUS_STYLES: dict[str, tuple[str, str, str]] = {
    "aprobado":     ("#10b981", "#f0fdf4", "#bbf7d0"),
    "en revision":  ("#f59e0b", "#fef3c7", "#fde68a"),
    "rechazado":    ("#ef4444", "#fef2f2", "#fecaca"),
    "pendiente":    ("#94a3b8", "#f1f5f9", "#e2e8f0"),
    "sin estado":   ("#94a3b8", "#f1f5f9", "#e2e8f0"),
}


def status_badge(status_name: str) -> str:
    """Return HTML string for a colored status badge."""
    key = status_name.lower().strip()
    color, bg, border = _STATUS_STYLES.get(key, ("#94a3b8", "#f1f5f9", "#e2e8f0"))
    return (
        f'<span class="status-badge" '
        f'style="background:{bg};border-color:{border};color:{color}">'
        f'{status_name}</span>'
    )


def render_section_header(title: str) -> None:
    """Render a styled section header with blue left border."""
    st.markdown(
        f'<div class="form-section-header">{title}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    """Render the branded sidebar header with logo icon."""
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-icon">TS</div>
            <div>
                <div class="sidebar-brand-text">Trading Solutions</div>
                <div class="sidebar-brand-sub">Compliance Platform</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_user(name: str, email: str) -> None:
    """Render user info in sidebar footer with name and email."""
    initials = "".join(w[0].upper() for w in name.split()[:2]) if name else "?"
    st.markdown(
        f"""
        <div class="sidebar-user">
            <div class="sidebar-user-row">
                <div class="sidebar-user-avatar">{initials}</div>
                <div class="sidebar-user-info">
                    <div class="sidebar-user-name">{name}</div>
                    <div class="sidebar-user-email">{email}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
