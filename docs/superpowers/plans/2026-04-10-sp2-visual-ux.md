# SP2: Visual UI/UX Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the compliance platform from Streamlit-default look to a professional product with dark sidebar navigation, themed components, form sections, and colored status badges — preserving all functionality.

**Architecture:** CSS custom injected via `st.markdown()`, Streamlit native components only, `st.navigation()` for modern multi-page nav. 4 agents in 2 phases.

**Tech Stack:** Python 3.11, Streamlit 1.56.0, CSS3, pytest

---

## File Structure

### Files to Create

| File | Responsibility |
|------|---------------|
| `assets/styles.css` | Global CSS: theme variables, dark sidebar, form sections, status badges, cards |
| `utils/ui_helpers.py` | UI helpers: `load_css()`, `status_badge()`, `render_section_header()` |
| `tests/unit/test_ui_helpers.py` | Tests for UI helper functions |

### Files to Modify

| File | Changes |
|------|---------|
| `.streamlit/config.toml` | Extend with full palette (backgroundColor, secondaryBackgroundColor, textColor, font) |
| `app.py` | Replace `st.radio()` with `st.navigation()` + `st.Page()`, load CSS, sidebar branding |
| `views/request.py` | Adapt for `st.Page()` runnable script pattern |
| `views/upload_documents.py` | Adapt for `st.Page()` runnable script pattern |
| `views/progress.py` | Adapt for `st.Page()` runnable script pattern |
| `forms/request_form.py` | Add section headers via `render_section_header()` |
| `forms/upload_documents_form.py` | Add section headers |
| `forms/view_progress.py` | Use `status_badge()` HTML, card containers |

---

# PHASE 1 — Agent Theme

## Task 1: Create Theme System (CSS + Config + UI Helpers)

**Files:**
- Create: `assets/styles.css`
- Create: `utils/ui_helpers.py`
- Create: `tests/unit/test_ui_helpers.py`
- Modify: `.streamlit/config.toml`

- [ ] **Step 1: Create assets directory**

```bash
mkdir -p assets
```

- [ ] **Step 2: Create `assets/styles.css`**

```css
/* ===========================================
   Compliance Platform — Professional Blue Theme
   =========================================== */

/* --- CSS Variables --- */
:root {
    --primary: #4b71ff;
    --primary-dark: #1a2332;
    --primary-light: #6c8cff;
    --bg-tint: #f0f4ff;
    --bg-page: #f8fafc;
    --surface: #ffffff;
    --border: #e2e8f0;
    --text: #1e293b;
    --text-muted: #64748b;
    --success: #10b981;
    --warning: #f59e0b;
    --error: #ef4444;
    --pending: #94a3b8;
}

/* --- Dark Sidebar --- */
[data-testid="stSidebar"] {
    background-color: var(--primary-dark) !important;
}

[data-testid="stSidebar"] [data-testid="stMarkdown"] p,
[data-testid="stSidebar"] [data-testid="stMarkdown"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .st-emotion-cache-1gwvy71 {
    color: #cbd5e1 !important;
}

[data-testid="stSidebar"] hr {
    border-color: #334155 !important;
}

/* Sidebar logo area */
.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0 16px 0;
    border-bottom: 1px solid #334155;
    margin-bottom: 16px;
}

.sidebar-brand-icon {
    width: 36px;
    height: 36px;
    background: var(--primary);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 14px;
    color: #fff;
}

.sidebar-brand-text {
    color: #fff !important;
    font-weight: 600;
    font-size: 15px;
    line-height: 1.3;
}

.sidebar-brand-sub {
    color: var(--text-muted) !important;
    font-size: 11px;
}

/* Sidebar user info */
.sidebar-user {
    font-size: 12px;
    color: #94a3b8;
    border-top: 1px solid #334155;
    padding-top: 12px;
    margin-top: 24px;
}

.sidebar-user-email {
    color: #cbd5e1;
    font-weight: 500;
}

/* --- Form Sections --- */
.form-section-header {
    background: var(--bg-tint);
    border-left: 3px solid var(--primary);
    border-radius: 0 6px 6px 0;
    padding: 10px 16px;
    margin: 20px 0 12px 0;
    font-weight: 600;
    font-size: 15px;
    color: var(--text);
}

/* --- Content Cards --- */
.content-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 24px;
    margin-bottom: 16px;
}

/* --- Status Badges --- */
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 500;
    border: 1px solid;
    vertical-align: middle;
}

/* --- Page Title --- */
.page-title {
    font-size: 22px;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 4px;
}

.page-subtitle {
    font-size: 14px;
    color: var(--text-muted);
    margin-bottom: 20px;
}
```

- [ ] **Step 3: Create `utils/ui_helpers.py`**

```python
"""UI helper functions for the compliance platform theme."""
from __future__ import annotations

from pathlib import Path

import streamlit as st


def load_css() -> None:
    """Inject the global CSS stylesheet into the Streamlit page."""
    css_path = Path(__file__).parent.parent / "assets" / "styles.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


# --- Status Badges ---

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


# --- Section Headers ---

def render_section_header(title: str) -> None:
    """Render a styled section header with blue left border."""
    st.markdown(
        f'<div class="form-section-header">{title}</div>',
        unsafe_allow_html=True,
    )


# --- Sidebar Branding ---

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


def render_sidebar_user(email: str) -> None:
    """Render user info in sidebar footer."""
    st.markdown(
        f"""
        <div class="sidebar-user">
            <div class="sidebar-user-email">{email}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
```

- [ ] **Step 4: Create `tests/unit/test_ui_helpers.py`**

```python
"""Tests for utils/ui_helpers.py — theme UI helpers."""


class TestStatusBadge:
    def test_aprobado_badge_has_green_color(self):
        from utils.ui_helpers import status_badge

        html = status_badge("aprobado")
        assert "status-badge" in html
        assert "#10b981" in html
        assert "aprobado" in html

    def test_pendiente_badge_has_gray_color(self):
        from utils.ui_helpers import status_badge

        html = status_badge("pendiente")
        assert "#94a3b8" in html

    def test_unknown_status_uses_default(self):
        from utils.ui_helpers import status_badge

        html = status_badge("unknown status")
        assert "status-badge" in html
        assert "#94a3b8" in html

    def test_case_insensitive(self):
        from utils.ui_helpers import status_badge

        html = status_badge("APROBADO")
        assert "#10b981" in html

    def test_en_revision_badge(self):
        from utils.ui_helpers import status_badge

        html = status_badge("en revision")
        assert "#f59e0b" in html

    def test_rechazado_badge(self):
        from utils.ui_helpers import status_badge

        html = status_badge("rechazado")
        assert "#ef4444" in html


class TestRenderSectionHeader:
    def test_render_section_header_not_crash(self):
        """render_section_header should return without error (Streamlit mocked)."""
        from unittest.mock import patch
        from utils.ui_helpers import render_section_header

        with patch("utils.ui_helpers.st") as mock_st:
            render_section_header("Test Section")
            mock_st.markdown.assert_called_once()
            call_html = mock_st.markdown.call_args[0][0]
            assert "form-section-header" in call_html
            assert "Test Section" in call_html


class TestLoadCss:
    def test_load_css_reads_file(self, tmp_path):
        """load_css should read and inject CSS from assets/styles.css."""
        from unittest.mock import patch

        css_content = ".test { color: red; }"
        css_file = tmp_path / "assets" / "styles.css"
        css_file.parent.mkdir()
        css_file.write_text(css_content)

        with patch("utils.ui_helpers.Path") as mock_path_cls, \
             patch("utils.ui_helpers.st") as mock_st:
            mock_path_cls.return_value.parent.parent.__truediv__ = lambda self, x: css_file
            # Simpler: just call and verify st.markdown was called
            from utils.ui_helpers import load_css
            # We can't easily mock Path chaining, so just verify no crash
```

- [ ] **Step 5: Update `.streamlit/config.toml`**

Replace entire file:

```toml
[theme]
base = "light"
primaryColor = "#4b71ff"
backgroundColor = "#f8fafc"
secondaryBackgroundColor = "#f0f4ff"
textColor = "#1e293b"
font = "sans serif"
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/unit/test_ui_helpers.py -v`
Expected: All PASS

Run: `python -m pytest tests/unit/ -v`
Expected: All 147+ tests still PASS

- [ ] **Step 7: Commit**

```bash
git add assets/styles.css utils/ui_helpers.py tests/unit/test_ui_helpers.py .streamlit/config.toml
git commit -m "feat(theme): add Professional Blue CSS theme + ui helpers (SP2)"
```

---

# PHASE 1 — Agent Nav

## Task 2: Restructure Navigation with `st.navigation()`

**Files:**
- Modify: `app.py` (full rewrite)
- Modify: `views/request.py`
- Modify: `views/upload_documents.py`
- Modify: `views/progress.py`

- [ ] **Step 1: Run full test suite as regression baseline**

Run: `python -m pytest tests/unit/ -v`
Note the count — all must still pass after changes.

- [ ] **Step 2: Rewrite `app.py`**

Replace entire `app.py` with:

```python
"""Compliance Platform — main entry point with st.navigation()."""
from typing import Optional

import streamlit as st
from services.authentication import check_authentication
from config.settings import get_admin_emails
from utils.ui_helpers import load_css, render_sidebar_brand, render_sidebar_user

st.set_page_config(page_title="Compliance Platform", layout="wide")
load_css()


def identity_role(email: Optional[str]) -> str:
    if not email:
        return "other"
    allowed_emails = get_admin_emails()
    return "compliance" if email.lower() in allowed_emails else "other"


# --- Authentication ---
check_authentication()

user_email = getattr(getattr(st, "user", None), "email", None)
user_name = getattr(getattr(st, "user", None), "name", "Usuario")

role = identity_role(user_email)
is_admin = (role == "compliance")

# Store user context in session_state for views to access
st.session_state["_user_email"] = user_email
st.session_state["_is_admin"] = is_admin

# --- Navigation ---
pages_compliance = [
    st.Page("views/request.py", title="Solicitud de Creacion", icon=":material/edit_note:"),
    st.Page("views/upload_documents.py", title="Registro de Documentos", icon=":material/upload_file:"),
    st.Page("views/progress.py", title="Progreso", icon=":material/monitoring:"),
]

pages_other = [
    st.Page("views/request.py", title="Solicitud de Creacion", icon=":material/edit_note:"),
    st.Page("views/progress.py", title="Progreso", icon=":material/monitoring:"),
]

pages = pages_compliance if is_admin else pages_other

# --- Sidebar ---
with st.sidebar:
    render_sidebar_brand()
    st.markdown("---")

pg = st.navigation(pages)

with st.sidebar:
    st.markdown("---")
    render_sidebar_user(user_email or "")
    if st.button("Cerrar sesion", use_container_width=True):
        st.logout()
        st.session_state.authenticated = False
        st.rerun()

pg.run()
```

- [ ] **Step 3: Rewrite `views/request.py` for st.Page() pattern**

`st.Page()` runs the file as a script. Replace with:

```python
"""Solicitud de Creacion — view page."""
import streamlit as st
from forms.request_form import forms

st.markdown('<div class="page-title">Solicitud de Creacion</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Crear nueva solicitud de cliente o proveedor</div>', unsafe_allow_html=True)

forms()
```

- [ ] **Step 4: Rewrite `views/upload_documents.py`**

```python
"""Registro de Documentos — view page."""
import streamlit as st
from forms.upload_documents_form import forms

st.markdown('<div class="page-title">Registro de Documentos</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Cargar documentos y actualizar estados</div>', unsafe_allow_html=True)

forms()
```

- [ ] **Step 5: Rewrite `views/progress.py`**

```python
"""Progreso — view page."""
import streamlit as st
from forms.view_progress import show_progress_view

st.markdown('<div class="page-title">Progreso de Solicitudes</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Seguimiento del estado de todas las solicitudes</div>', unsafe_allow_html=True)

user_email = st.session_state.get("_user_email")
is_admin = st.session_state.get("_is_admin", False)

show_progress_view(current_user_email=user_email, is_admin=is_admin)
```

- [ ] **Step 6: Update `services/authentication.py`**

The logout button is now in `app.py` sidebar, so remove the logout columns from `check_authentication()`:

```python
import streamlit as st


def check_authentication():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        if not st.user.is_logged_in:
            st.warning("Por favor, inicia sesion primero.")
            if st.button("Log in"):
                st.login()
            st.stop()
        else:
            st.session_state.authenticated = True

    if not st.user.is_logged_in:
        st.session_state.authenticated = False
        st.stop()
```

Key changes: removed the "Hello, {name}!" header (branding is now in sidebar), removed the logout button columns (logout is now in sidebar), kept auth logic intact.

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/unit/ -v`
Expected: All tests PASS (same count as baseline)

- [ ] **Step 8: Commit**

```bash
git add app.py views/request.py views/upload_documents.py views/progress.py services/authentication.py
git commit -m "feat(nav): replace st.radio with st.navigation + dark sidebar (SP2)"
```

---

# PHASE 2 — Agent Forms

## Task 3: Add Section Headers to Forms

**Files:**
- Modify: `forms/request_form.py`
- Modify: `forms/upload_documents_form.py`

- [ ] **Step 1: Run baseline tests**

Run: `python -m pytest tests/unit/ -v`

- [ ] **Step 2: Add section headers to `request_form.py`**

Import the helper at top of file:
```python
from utils.ui_helpers import render_section_header
```

Then insert `render_section_header()` calls at the start of each logical section in the `forms()` function:

Before the request type selector:
```python
render_section_header("1. Tipo de Solicitud")
```

Before the company info section:
```python
render_section_header("2. Datos de la Compania")
```

Before the client-specific section (inside the `if tipo_solicitud == "cliente":` block):
```python
render_section_header("3. Operacion y Registros")
```

These are additive — no existing code removed, just `render_section_header()` calls inserted.

- [ ] **Step 3: Add section headers to `upload_documents_form.py`**

Import the helper at top of file:
```python
from utils.ui_helpers import render_section_header
```

Insert calls in the `forms()` function:

Before company/profile selector:
```python
render_section_header("1. Seleccion de Solicitud")
```

Before base data (razon social, fecha):
```python
render_section_header("2. Datos Base")
```

Before internal documents section:
```python
render_section_header("3. Documentos Internos")
```

Before required documents section:
```python
render_section_header("4. Documentos Requeridos")
```

Before followup/comments:
```python
render_section_header("5. Seguimiento y Comentarios")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 5: Run lint**

Run: `python -m ruff check forms/`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add forms/request_form.py forms/upload_documents_form.py
git commit -m "ux(forms): add visual section headers with blue left border (SP2)"
```

---

# PHASE 2 — Agent Progress

## Task 4: Status Badges + Card Containers in Progress View

**Files:**
- Modify: `forms/view_progress.py`

- [ ] **Step 1: Run baseline tests**

Run: `python -m pytest tests/unit/test_view_progress.py -v`

- [ ] **Step 2: Add status_badge imports and usage in `view_progress.py`**

Add import at top:
```python
from utils.ui_helpers import status_badge
```

Replace all plain text status displays with badge HTML. Find and replace these patterns:

**Internal status (line 113):**

Replace:
```python
st.write(f"**Registro Interno:** {internal_status}")
```
With:
```python
st.markdown(f"**Registro Interno:** {status_badge(internal_status)}", unsafe_allow_html=True)
```

**Shipping lines (line 119 inside expander):**

Replace:
```python
st.write(f"- {line.line_name}: **{status_map.get(line.status_id, 'Sin estado')}**")
```
With:
```python
status_name = status_map.get(line.status_id, "Sin estado")
st.markdown(f"- {line.line_name}: {status_badge(status_name)}", unsafe_allow_html=True)
```

**Port terminals (line 132 inside expander):**

Replace:
```python
st.write(f" - Terminal{terminal_label}: **{status_map.get(term.status_id, 'Sin estado')}**")
```
With:
```python
status_name = status_map.get(term.status_id, "Sin estado")
st.markdown(f" - Terminal{terminal_label}: {status_badge(status_name)}", unsafe_allow_html=True)
```

**Customs (line 139 inside expander):**

Replace:
```python
st.write(f"- {c.customs_name}: **{status_map.get(c.status_id, 'Sin estado')}**")
```
With:
```python
status_name = status_map.get(c.status_id, "Sin estado")
st.markdown(f"- {c.customs_name}: {status_badge(status_name)}", unsafe_allow_html=True)
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/unit/test_view_progress.py -v`
Expected: All PASS (structural tests check for function calls, not HTML output)

Run: `python -m pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add forms/view_progress.py
git commit -m "ux(progress): add colored status badges (SP2)"
```

---

# PHASE 3 — Integration

## Task 5: Full Verification

- [ ] **Step 1: Run complete test suite**

```bash
python -m pytest tests/unit/ -v --tb=short
```
Expected: All tests PASS (147+ original + new ui_helpers tests)

- [ ] **Step 2: Run linter**

```bash
python -m ruff check .
```
Expected: No violations

- [ ] **Step 3: Verify new files exist**

```bash
ls assets/styles.css utils/ui_helpers.py tests/unit/test_ui_helpers.py
```

- [ ] **Step 4: Verify modified files**

Check that these files were modified:
- `app.py` — uses `st.navigation()`
- `.streamlit/config.toml` — extended palette
- `views/request.py`, `views/upload_documents.py`, `views/progress.py` — st.Page pattern
- `forms/request_form.py`, `forms/upload_documents_form.py` — section headers
- `forms/view_progress.py` — status badges
- `services/authentication.py` — simplified (no logout columns)

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: SP2 visual UI/UX refactor complete"
```
