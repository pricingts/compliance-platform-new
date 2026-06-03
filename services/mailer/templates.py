"""HTML template renderer for the compliance platform's notification emails.

The rendered email mirrors the layout used by the legacy Apps Script notifier:
a blue "NEW REQUEST" header, a prominent Case ID banner, a two-column table of
fields and values, and a small footer. All values are HTML-escaped via
``html.escape`` to guarantee XSS safety.

Keys accepted in ``payload`` overlap with ``services.sheets_writer.save_request``
so callers can reuse the same dict they already assemble for the Google Sheet.
"""
from __future__ import annotations

import html
from typing import Optional


# Ordered list of (payload_key, display_label). Mirrors the Sheets column set
# so the email shows exactly what the Sheet stores, in the same order.
_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("requested_by", "Solicitante"),
    ("tipo_solicitud", "Tipo de solicitud"),
    ("company_name", "Nombre Compañía"),
    ("email", "Correo"),
    ("trading", "Cuenta Trading"),
    ("location", "País / Ubicación"),
    ("language", "Idioma"),
    ("reminder_frequency", "Frecuencia Recordatorio"),
    ("tipo_operacion", "Tipo de Operación"),
    ("commodity", "Commodity"),
    ("aduana", "Aduana"),
    ("puerto", "Puerto"),
    ("linea_naviera", "Línea Naviera"),
    # MSC shipping detail + free-text notes from the comercial. Empty values are
    # skipped by the renderer, so these rows only appear when actually filled.
    ("pol", "POL (Puerto de Origen)"),
    ("pod", "POD (Puerto de Destino)"),
    ("producto", "Producto"),
    ("tipo_contenedor", "Tipo de Contenedor"),
    ("shipper_bl", "¿Cómo saldrá el Shipper en BL?"),
    ("notes", "Notas para Compliance"),
)


def _is_empty(value) -> bool:
    """Mirror the Apps Script ``isEmptyCell`` behavior."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _row(label: str, value) -> str:
    """Render a single <tr> for the fields table. Values are escaped."""
    return (
        f"<tr><th>{html.escape(label)}</th>"
        f"<td>{html.escape(str(value))}</td></tr>"
    )


def _render_sender_banner(
    creator_email: Optional[str], submitted_by_email: Optional[str]
) -> str:
    """Return a highlighted banner disclosing the IS → comercial relay.

    Rendered only when ``submitted_by_email`` is set AND differs from
    ``creator_email`` after normalizing (``lower().strip()``). Returns an
    empty string in all other cases so callers can concatenate blindly.

    Both addresses are HTML-escaped (XSS-safe).
    """
    if not submitted_by_email:
        return ""
    creator_norm = (creator_email or "").strip().lower()
    submitted_norm = submitted_by_email.strip().lower()
    if not submitted_norm or submitted_norm == creator_norm:
        return ""

    creator_disp = html.escape(creator_email or "")
    submitted_disp = html.escape(submitted_by_email)
    return (
        '<div class="sender-banner" style="background-color:#fff3cd; '
        'border-left:4px solid #ffc107; padding:10px; margin-bottom:12px; '
        'font-size:0.95rem;">'
        f'<strong>Enviado por:</strong> {creator_disp}<br>'
        f'<strong>En nombre de:</strong> {submitted_disp}'
        '</div>'
    )


def render_request_email(
    case_id: str,
    payload: dict,
    *,
    creator_email: Optional[str] = None,
    submitted_by_email: Optional[str] = None,
) -> tuple[str, str]:
    """Render subject + HTML body for a new-request notification.

    Args:
        case_id: Case identifier (e.g. ``"C0042"``) shown in subject and banner.
        payload: A dict of request fields. Keys that match ``_FIELD_MAP`` are
            rendered in a fixed order; empty values are omitted. Unknown keys
            are silently ignored.
        creator_email: Optional email of the form author. Combined with
            ``submitted_by_email`` to render an "Enviado por / En nombre de"
            banner when the two differ (Inside Sales creating on behalf of a
            comercial).
        submitted_by_email: Optional email of the person on whose behalf the
            form was submitted. See ``creator_email``.

    Returns:
        Tuple ``(subject, html_body)``.
    """
    company_name = payload.get("company_name", "") or ""
    subject = f"Solicitud de Registro - {case_id} - {company_name}"

    rows: list[str] = []
    for key, label in _FIELD_MAP:
        value = payload.get(key)
        if _is_empty(value):
            continue
        rows.append(_row(label, value))
    rows_html = "".join(rows)

    escaped_case_id = html.escape(case_id)
    sender_banner = _render_sender_banner(creator_email, submitted_by_email)

    html_body = f"""<html><head><style>
body {{ font-family: Arial, sans-serif; color: #333; }}
h2 {{ color: #007BFF; margin-bottom: 0.5rem; }}
.case-banner {{ background-color: #e6f2ff; border-left: 4px solid #007BFF; padding: 12px; margin-bottom: 16px; font-size: 1.1rem; }}
table {{ border-collapse: collapse; width: 100%; max-width: 600px; }}
th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
th {{ background-color: #f2f2f2; text-align: left; width: 30%; }}
tr:nth-child(even) {{ background-color: #fafafa; }}
.footer {{ margin-top: 1rem; font-size: 0.9rem; color: #666; }}
</style></head><body>
<h2>NEW REQUEST</h2>
{sender_banner}<div class="case-banner"><strong>Case ID:</strong> {escaped_case_id}</div>
<table>{rows_html}</table>
<p class="footer">Please review the information above.<br><em>Automated message from Compliance Platform</em></p>
</body></html>"""

    return subject, html_body
