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


def render_request_email(case_id: str, payload: dict) -> tuple[str, str]:
    """Render subject + HTML body for a new-request notification.

    Args:
        case_id: Case identifier (e.g. ``"C0042"``) shown in subject and banner.
        payload: A dict of request fields. Keys that match ``_FIELD_MAP`` are
            rendered in a fixed order; empty values are omitted. Unknown keys
            are silently ignored.

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
<div class="case-banner"><strong>Case ID:</strong> {escaped_case_id}</div>
<table>{rows_html}</table>
<p class="footer">Please review the information above.<br><em>Automated message from Compliance Platform</em></p>
</body></html>"""

    return subject, html_body
