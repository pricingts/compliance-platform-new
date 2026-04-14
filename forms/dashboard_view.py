"""Dashboard view logic — compliance KPIs, filterable table, CSV export."""
from __future__ import annotations

import io
from datetime import datetime, timedelta

from utils.timezone import utc_now

import pandas as pd
import streamlit as st
from sqlalchemy import text

from database.db import SessionLocal
from utils.ui_helpers import render_section_header
from utils.timezone import to_colombia_tz


# ==========================
# QUERIES
# ==========================

def _get_dashboard_data(session) -> pd.DataFrame:
    """Fetch all requests with aggregated status counts."""
    rows = session.execute(text("""
        SELECT
            r.id,
            r.case_id,
            r.company_name,
            r.profile_id,
            p.name AS profile_name,
            r.commercial,
            r.trading,
            r.country,
            r.email,
            r.user_email,
            r.submitted_by_email,
            r.created_at,
            r.has_customs,
            r.has_port,
            r.has_shipping_line
        FROM requests r
        LEFT JOIN profiles p ON p.id = r.profile_id
        ORDER BY r.created_at DESC
    """)).fetchall()

    if not rows:
        return pd.DataFrame()

    data = [
        {
            "Case ID": r.case_id or f"C{r.id:04d}",
            "Empresa": r.company_name or "—",
            "Perfil": r.profile_name or "—",
            "Comercial": r.commercial or "—",
            "Trading": r.trading or "—",
            "Pais": r.country or "—",
            "Email": r.email or "—",
            "Creado por": r.user_email or "—",
            "Registrado por (IS)": r.submitted_by_email or "—",
            "Fecha creacion": r.created_at,
            "Aduana": "Si" if r.has_customs else "No",
            "Puerto": "Si" if r.has_port else "No",
            "Naviera": "Si" if r.has_shipping_line else "No",
        }
        for r in rows
    ]
    return pd.DataFrame(data)


def _get_status_summary(session) -> dict:
    """Get aggregated status counts across all registration types."""
    result = {}

    for table, name_col in [
        ("customs_registration", "customs_name"),
        ("port_registration", "port_name"),
        ("shipping_line_registration", "line_name"),
        ("internal_registration", "internal_label"),
    ]:
        rows = session.execute(text(f"""
            SELECT s.status, COUNT(*) as cnt
            FROM {table} t
            LEFT JOIN status s ON s.id = t.status_id
            GROUP BY s.status
        """)).fetchall()

        for r in rows:
            status_name = r.status or "sin estado"
            result[status_name] = result.get(status_name, 0) + r.cnt

    return result


def _get_recent_activity(session, limit: int = 10) -> list[dict]:
    """Get most recent audit log entries."""
    rows = session.execute(text("""
        SELECT timestamp, user_email, action, entity_type, details
        FROM audit_log
        ORDER BY timestamp DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    return [
        {
            "timestamp": r.timestamp,
            "user_email": r.user_email,
            "action": r.action,
            "entity_type": r.entity_type,
            "details": r.details,
        }
        for r in rows
    ]


# ==========================
# DASHBOARD VIEW
# ==========================

def show_dashboard():
    session = SessionLocal()

    try:
        df = _get_dashboard_data(session)

        if df.empty:
            st.info("No hay solicitudes registradas.")
            return

        # === KPI Cards ===
        render_section_header("Indicadores Clave")

        total = len(df)
        try:
            cutoff = utc_now() - timedelta(days=7)
            # Handle both naive and aware timestamps
            last_7_days = len(df[df["Fecha creacion"].apply(
                lambda x: x.replace(tzinfo=None) if hasattr(x, 'tzinfo') and x.tzinfo else x
            ) >= cutoff]) if "Fecha creacion" in df.columns else 0
        except Exception:
            last_7_days = 0

        status_summary = _get_status_summary(session)
        aprobados = status_summary.get("aprobado", 0)
        pendientes = status_summary.get("pendiente", 0)
        en_revision = status_summary.get("en revision", 0)
        rechazados = status_summary.get("rechazado", 0)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total solicitudes", total)
        with col2:
            st.metric("Ultimos 7 dias", last_7_days)
        with col3:
            st.metric("Aprobados", aprobados)
        with col4:
            st.metric("En revision", en_revision)
        with col5:
            st.metric("Rechazados", rechazados)

        st.markdown("---")

        # === Filters ===
        render_section_header("Solicitudes")

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)

        with col_f1:
            empresas = ["Todas"] + sorted(df["Empresa"].unique().tolist())
            empresa_filter = st.selectbox("Empresa", empresas)

        with col_f2:
            perfiles = ["Todos"] + sorted(df["Perfil"].unique().tolist())
            perfil_filter = st.selectbox("Perfil", perfiles)

        with col_f3:
            tradings = ["Todos"] + sorted(df["Trading"].unique().tolist())
            trading_filter = st.selectbox("Trading", tradings)

        with col_f4:
            comerciales = ["Todos"] + sorted(df["Comercial"].unique().tolist())
            comercial_filter = st.selectbox("Comercial", comerciales)

        # Apply filters
        filtered = df.copy()
        if empresa_filter != "Todas":
            filtered = filtered[filtered["Empresa"] == empresa_filter]
        if perfil_filter != "Todos":
            filtered = filtered[filtered["Perfil"] == perfil_filter]
        if trading_filter != "Todos":
            filtered = filtered[filtered["Trading"] == trading_filter]
        if comercial_filter != "Todos":
            filtered = filtered[filtered["Comercial"] == comercial_filter]

        st.caption(f"Mostrando {len(filtered)} de {total} solicitudes")

        # === Table ===
        display_cols = ["Case ID", "Empresa", "Perfil", "Comercial", "Trading", "Pais", "Fecha creacion", "Aduana", "Puerto", "Naviera"]
        st.dataframe(
            filtered[display_cols],
            width="stretch",
            hide_index=True,
        )

        # === CSV Export (with UTF-8 BOM for Excel) ===
        csv_buffer = io.BytesIO()
        csv_buffer.write(b'\xef\xbb\xbf')  # UTF-8 BOM for Excel
        filtered.to_csv(csv_buffer, index=False, encoding='utf-8')
        st.download_button(
            "Exportar CSV",
            csv_buffer.getvalue(),
            file_name=f"compliance_solicitudes_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

        st.markdown("---")

        # === Status Distribution ===
        render_section_header("Distribucion de Estados")

        if status_summary:
            status_df = pd.DataFrame(
                list(status_summary.items()),
                columns=["Estado", "Cantidad"]
            )
            st.bar_chart(status_df.set_index("Estado"))
        else:
            st.caption("Sin datos de estado disponibles.")

        st.markdown("---")

        # === Recent Activity ===
        render_section_header("Actividad Reciente")

        activity = _get_recent_activity(session)
        if activity:
            for event in activity:
                ts = event["timestamp"]
                ts_str = to_colombia_tz(ts).strftime("%Y-%m-%d %H:%M") if ts else "—"
                action_icons = {
                    "CREATE": "🆕",
                    "UPLOAD": "📎",
                    "STATUS_CHANGE": "🔄",
                    "UPDATE": "✏️",
                }
                icon = action_icons.get(event["action"], "•")
                user = (event["user_email"] or "—").split("@")[0]
                detail = event["details"] or event["action"]
                st.markdown(f"{icon} **{ts_str}** - {user} - {detail}")
        else:
            st.caption("Sin actividad reciente registrada.")

    finally:
        session.close()
