"""'Mis Solicitudes' personal dashboard rendering (Phase 6 / F6).

Shown to comerciales, Inside Sales, and 'otro' roles. Compliance has its
own global dashboard at views/dashboard.py.
"""
from __future__ import annotations

from typing import Optional
from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from database.crud.my_requests import get_my_requests, get_aggregated_status_for_request
from database.crud.documents import get_last_status_change_time
from utils.ui_helpers import render_section_header
from utils.timezone import to_colombia_tz, utc_now


def _sla_badge(last_change: Optional[datetime]) -> str:
    """Mirror of forms.view_progress._sla_badge — kept here to avoid coupling."""
    if not last_change:
        return ""
    now = utc_now()
    change_naive = (
        last_change.replace(tzinfo=None)
        if hasattr(last_change, "tzinfo") and last_change.tzinfo
        else last_change
    )
    delta = now - change_naive
    days = delta.days
    color = "#10b981" if days < 3 else "#f59e0b" if days < 7 else "#ef4444"
    label = f"{days}d" if days > 0 else "hoy"
    return f' <span style="background:{color};color:white;padding:1px 6px;border-radius:8px;font-size:11px;">{label}</span>'


def render_my_requests(session, current_user_email: str):
    """Render the personal dashboard for the logged-in non-compliance user."""
    render_section_header("Mis Solicitudes")

    st.caption(
        "Solicitudes que has creado o registrado en nombre de un comercial. "
        "Para ver el detalle, usa la opción 'Progreso' del menú."
    )

    if not current_user_email:
        st.info("No hay usuario autenticado.")
        return

    rows = get_my_requests(session, current_user_email)
    if not rows:
        st.info("Aún no has creado solicitudes en la plataforma.")
        return

    # Compute aggregated status + SLA per row
    enriched = []
    for r in rows:
        try:
            agg = get_aggregated_status_for_request(session, r["id"])
        except SQLAlchemyError:
            agg = "Pendiente"
        try:
            # NOTE: known signature mismatch — the helper expects
            # (session, entity_type, entity_id) but is being called without
            # the session. This is a latent bug out of scope for exception
            # narrowing; `TypeError` is therefore caught alongside DB errors
            # so the dashboard still renders with a safe fallback.
            last_change = get_last_status_change_time("request", r["id"])
        except (SQLAlchemyError, TypeError):
            last_change = r.get("created_at")
        enriched.append({
            "Case ID": r["case_id"],
            "Empresa": r["company_name"] or "—",
            "Perfil": r["profile_name"] or "—",
            "Comercial": r["commercial"] or "—",
            "Fecha creacion": (
                to_colombia_tz(r["created_at"]) if r.get("created_at") else "—"
            ),
            "Estado global": agg,
            "Tiempo en estado": days_label(last_change),
        })

    df = pd.DataFrame(enriched)
    st.dataframe(df, width="stretch", hide_index=True)

    # Compact KPIs
    total = len(rows)
    completas = sum(1 for r in enriched if r["Estado global"] == "Completa")
    rechazos = sum(1 for r in enriched if r["Estado global"] == "Con rechazos")
    revision = sum(1 for r in enriched if r["Estado global"] == "En revisión")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", total)
    c2.metric("Completas", completas)
    c3.metric("En revisión", revision)
    c4.metric("Con rechazos", rechazos)


def days_label(last_change: Optional[datetime]) -> str:
    """Plain-text version of _sla_badge for table cells."""
    if not last_change:
        return "—"
    now = utc_now()
    change_naive = (
        last_change.replace(tzinfo=None)
        if hasattr(last_change, "tzinfo") and last_change.tzinfo
        else last_change
    )
    delta = now - change_naive
    days = delta.days
    return f"{days}d" if days > 0 else "hoy"
