# SP2: Visual UI/UX Refactor — Design Spec

## Context

The compliance platform for Trading Solutions is functionally solid after SP1 (bug fixes + robustness). However, it uses Streamlit defaults heavily — basic `st.radio()` navigation, no custom CSS, no visual hierarchy in forms, plain text statuses. This refactor transforms the platform from prototype-looking to professional product without losing any functionality.

**Constraint:** Zero functionality loss. Every visual change preserves 100% of existing behavior.

**Approach:** CSS Custom + Streamlit Native Components. No external dependencies added.

**Methodology:** Agent teams with TDD (regression-first), same as SP1.

---

## 1. Color System & Theme

### Palette: Professional Blue

| Token | Hex | Usage |
|-------|-----|-------|
| `--primary` | `#4b71ff` | Buttons, active nav, links |
| `--primary-dark` | `#1a2332` | Sidebar background, headers |
| `--primary-light` | `#6c8cff` | Hover states |
| `--bg-tint` | `#f0f4ff` | Section backgrounds, form groups |
| `--bg-page` | `#f8fafc` | Main content area background |
| `--surface` | `#ffffff` | Cards, form surfaces |
| `--border` | `#e2e8f0` | Card borders, dividers |
| `--text` | `#1e293b` | Primary text |
| `--text-muted` | `#64748b` | Labels, placeholders, captions |
| `--success` | `#10b981` | Aprobado status |
| `--warning` | `#f59e0b` | En Revisión status |
| `--error` | `#ef4444` | Rechazado status |
| `--pending` | `#94a3b8` | Pendiente status |

### Implementation

**File:** `assets/styles.css` — injected in `app.py` via:
```python
from pathlib import Path

def load_css():
    css_path = Path(__file__).parent / "assets" / "styles.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)
```

**File:** `.streamlit/config.toml` — extended:
```toml
[theme]
base = "light"
primaryColor = "#4b71ff"
backgroundColor = "#f8fafc"
secondaryBackgroundColor = "#f0f4ff"
textColor = "#1e293b"
font = "sans serif"
```

---

## 2. Navigation & Layout

### Change: Replace `st.radio()` with `st.navigation()` + `st.Page()`

Streamlit >= 1.36 supports `st.navigation()` which provides native multi-page navigation in the sidebar with icons, grouping, and automatic URL routing.

**Current (`app.py`):**
```python
page = st.radio("Go to", allowed_pages, index=0)
if page == "Solicitud de Creación":
    import views.request as r
    r.show()
```

**New (`app.py`):**
```python
pages_compliance = [
    st.Page("views/request.py", title="Solicitud de Creacion", icon=":material/edit_note:"),
    st.Page("views/upload_documents.py", title="Registro de Documentos", icon=":material/upload_file:"),
    st.Page("views/progress.py", title="Progreso", icon=":material/monitoring:"),
]
pages_other = [
    st.Page("views/request.py", title="Solicitud de Creacion", icon=":material/edit_note:"),
    st.Page("views/progress.py", title="Progreso", icon=":material/monitoring:"),
]

pages = pages_compliance if role == "compliance" else pages_other
pg = st.navigation(pages)
pg.run()
```

### Sidebar Styling (CSS)

The sidebar gets a dark navy treatment via CSS targeting Streamlit's sidebar classes:
- Background: `#1a2332`
- Nav items: white text, `#94a3b8` for inactive
- Active item: `#4b71ff` background pill with white text
- Logo + "Trading Solutions" / "Compliance Platform" at top
- User email + "Cerrar sesión" at bottom

### View Wrappers

`st.Page()` expects each view file to be a runnable script. The current `views/*.py` wrappers call form functions — this pattern is preserved. Each view file:
1. Loads CSS (if not already loaded via app.py)
2. Shows page title with consistent styling
3. Calls the form function

---

## 3. Form UX Improvements

### Grouped Sections

Wrap related form fields in visually distinct sections using `st.container()` + custom CSS:

```python
def render_section(title: str):
    """Return a container styled as a form section with blue left border."""
    st.markdown(f"""
        <div class="form-section">
            <div class="form-section-title">{title}</div>
        </div>
    """, unsafe_allow_html=True)
```

**CSS class `.form-section`:**
- Background: `#f0f4ff`
- Left border: 3px solid `#4b71ff`
- Border-radius: 0 6px 6px 0
- Padding: 16px
- Margin-bottom: 16px

### Section Structure for Request Form

| Section | Title | Fields |
|---------|-------|--------|
| 1 | Tipo de Solicitud | tipo_solicitud, comercial/solicitante |
| 2 | Datos de la Compañía | nombre, email, trading, país, idioma, frecuencia |
| 3 | Operación (solo cliente) | tipo_operacion, commodity |
| 4 | Registros Requeridos (solo cliente) | aduanas, puertos, líneas navieras + detalles MSC |

### Section Structure for Upload Form

| Section | Title | Fields |
|---------|-------|--------|
| 1 | Selección de Solicitud | compañía, perfil, request selector |
| 2 | Datos Base | razón social, fecha creación |
| 3 | Documentos Internos | file uploaders + status |
| 4 | Documentos Requeridos | file uploaders + expanders con statuses |
| 5 | Seguimiento | notificaciones, comentarios |

### Card-Style Containers for Content

Main content areas wrapped in white cards:
```css
.content-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 24px;
    margin-bottom: 16px;
}
```

---

## 4. Status Badges

### Replace plain text with colored badge HTML

**Helper function** in `utils/ui_helpers.py`:
```python
STATUS_COLORS = {
    "aprobado": ("--success", "#f0fdf4", "#bbf7d0"),
    "en revision": ("--warning", "#fef3c7", "#fde68a"),
    "rechazado": ("--error", "#fef2f2", "#fecaca"),
    "pendiente": ("--pending", "#f1f5f9", "#e2e8f0"),
}

def status_badge(status_name: str) -> str:
    """Return HTML for a colored status badge."""
    key = status_name.lower().strip()
    color_var, bg, border = STATUS_COLORS.get(key, ("--pending", "#f1f5f9", "#e2e8f0"))
    return f'<span class="status-badge" style="background:{bg};border-color:{border};color:var({color_var})">{status_name}</span>'
```

**CSS class `.status-badge`:**
```css
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 500;
    border: 1px solid;
}
```

**Usage in progress view:**
```python
st.markdown(f"- {line.line_name}: {status_badge(status_name)}", unsafe_allow_html=True)
```

---

## 5. File Architecture

### New Files

| File | Purpose |
|------|---------|
| `assets/styles.css` | Global CSS — theme, sidebar, form sections, badges, cards |
| `utils/ui_helpers.py` | UI helper functions: `status_badge()`, `render_section_header()`, `load_css()` |

### Modified Files

| File | Changes |
|------|---------|
| `app.py` | Replace st.radio with st.navigation, load CSS, restructure sidebar |
| `.streamlit/config.toml` | Extended theme with full palette |
| `views/request.py` | Adapt for st.Page() pattern |
| `views/upload_documents.py` | Adapt for st.Page() pattern |
| `views/progress.py` | Adapt for st.Page() pattern |
| `forms/request_form.py` | Wrap fields in sections, use constants for section titles |
| `forms/upload_documents_form.py` | Wrap fields in sections, use status badges |
| `forms/view_progress.py` | Use status badges, card containers |

### Existing Code to Reuse

- `config/constants.py` — all form constants (from SP1)
- `utils/form_helpers.py` — cached data wrappers (from SP1)
- `utils/session_helpers.py` — session context manager (from SP1)
- `services/authentication.py` — auth flow (unchanged)

---

## 6. Agent Teams

### Phase 1 (parallel — no file conflicts):

| Agent | Scope | Files |
|-------|-------|-------|
| **Agent Theme** | Create CSS + theme config + ui_helpers | `assets/styles.css`, `.streamlit/config.toml`, `utils/ui_helpers.py` + tests |
| **Agent Nav** | Restructure app.py with st.navigation + adapt views | `app.py`, `views/*.py` |

### Phase 2 (parallel — depends on Phase 1):

| Agent | Scope | Files |
|-------|-------|-------|
| **Agent Forms** | Wrap form fields in sections, use section headers | `forms/request_form.py`, `forms/upload_documents_form.py` |
| **Agent Progress** | Status badges + card containers in progress view | `forms/view_progress.py` |

### Phase 3 (sequential):
- Integration verification — all tests pass, visual smoke test

---

## 7. Verification Plan

1. **Unit tests:** `pytest tests/unit/ -v` — all 147+ tests pass
2. **Lint:** `ruff check .` — no violations
3. **Visual smoke test:**
   - Login as compliance → see 3 pages with icons in sidebar
   - Login as other → see 2 pages
   - Navigate between pages — URL changes, no page reload issues
   - Create request (cliente + proveedor) — all fields work
   - Upload documents — file upload + status controls work
   - View progress — badges show correct colors, pagination works
4. **Responsive check:** Wide + narrow layouts render correctly
5. **No functionality loss:** Every form submits data correctly, Google Drive upload works, Google Sheets sync works
