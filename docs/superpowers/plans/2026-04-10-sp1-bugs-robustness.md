# SP1: Critical Bugs + Platform Robustness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 2 confirmed bugs and add 12 robustness improvements to the compliance platform with zero functionality loss.

**Architecture:** 4 agent teams in 2 phases. Phase 1 (Agent DB + Agent Quality) runs in parallel with no file conflicts. Phase 2 (Agent Performance + Agent Validation) runs in parallel after Phase 1 completes. Each agent follows TDD regression-first: write regression tests capturing current behavior, write failing test exposing the issue, implement fix, verify all tests pass.

**Tech Stack:** Python 3.11, Streamlit 1.56.0, SQLAlchemy 2.0, PostgreSQL 14, pytest, SQLite (tests)

---

## File Structure

### Files to Create
| File | Responsibility |
|------|---------------|
| `config/constants.py` | All magic strings extracted from forms (terminals, countries, comerciales, etc.) |
| `utils/session_helpers.py` | Session context manager for safe DB session lifecycle |
| `utils/form_helpers.py` | Shared form patterns: cached data wrappers, selectbox builders, status display |

### Files to Modify
| File | Changes |
|------|---------|
| `init_db.sql` | Add `audit_log` table DDL + indexes |
| `database/crud/clientes.py` | Fix race condition with dialect-aware INSERT RETURNING |
| `database/crud/documents.py` | Add `batch_upsert_statuses()`, `get_requests_for_progress()` pagination |
| `forms/request_form.py` | Decompose into helpers, use constants, add validations, spinners, error handling |
| `forms/upload_documents_form.py` | Decompose into helpers, use constants, add file size validation, spinners, error handling |
| `forms/view_progress.py` | Use session helper, add pagination UI |
| `tests/conftest.py` | Already has audit_log — no changes needed |

---

# PHASE 1 — Agent DB

## Task 1: Add `audit_log` Table to Production Schema

**Files:**
- Modify: `init_db.sql` (after line 122)
- Test: `tests/unit/test_audit.py`

- [ ] **Step 1: Write regression test — existing tables still create correctly**

Add to `tests/unit/test_audit.py`:

```python
"""Tests for audit trail — schema and service."""
import pytest
from sqlalchemy import text


class TestAuditLogSchema:
    """Verify audit_log table exists and accepts inserts."""

    def test_audit_log_table_exists(self, db_session):
        """The audit_log table should exist in the test schema."""
        result = db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
        ).fetchone()
        assert result is not None, "audit_log table must exist"

    def test_audit_log_insert_and_read(self, db_session):
        """log_action should persist a row to audit_log."""
        from services.audit import log_action

        log_action(
            session=db_session,
            user_email="test@tradingsolutions.com",
            action="CREATE",
            entity_type="request",
            entity_id=1,
            new_value={"company_name": "Test Corp"},
            details="Created via test",
        )
        db_session.commit()

        row = db_session.execute(
            text("SELECT user_email, action, entity_type, entity_id, new_value, details FROM audit_log")
        ).fetchone()
        assert row is not None
        assert row[0] == "test@tradingsolutions.com"
        assert row[1] == "CREATE"
        assert row[2] == "request"
        assert row[3] == 1
        assert "Test Corp" in row[4]
        assert row[5] == "Created via test"

    def test_audit_log_nullable_fields(self, db_session):
        """entity_id, old_value, new_value, details should accept NULL."""
        from services.audit import log_action

        log_action(
            session=db_session,
            user_email="test@tradingsolutions.com",
            action="LOGIN",
            entity_type="session",
        )
        db_session.commit()

        row = db_session.execute(
            text("SELECT entity_id, old_value, new_value, details FROM audit_log")
        ).fetchone()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None
        assert row[3] is None
```

- [ ] **Step 2: Run tests to verify they pass (conftest.py already has audit_log)**

Run: `pytest tests/unit/test_audit.py -v`
Expected: PASS (conftest.py schema already includes audit_log at lines 115-125)

- [ ] **Step 3: Add audit_log table DDL to init_db.sql**

Add after line 122 of `init_db.sql` (after internal_registration):

```sql
-- =====================
-- 11. Tabla audit_log
-- =====================
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_email VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id INTEGER,
    old_value TEXT,
    new_value TEXT,
    details TEXT
);
```

- [ ] **Step 4: Run full test suite to verify no regressions**

Run: `pytest tests/unit/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add init_db.sql tests/unit/test_audit.py
git commit -m "fix(schema): add audit_log table to init_db.sql (B1)"
```

---

## Task 2: Fix Race Condition in `insert_client_request`

**Files:**
- Modify: `database/crud/clientes.py:36-86`
- Test: `tests/unit/test_clientes_crud.py`

- [ ] **Step 1: Write regression test — existing insert behavior preserved**

The existing `TestInsertClientRequest` tests at `tests/unit/test_clientes_crud.py:31-85` already cover this. Verify they pass first.

Run: `pytest tests/unit/test_clientes_crud.py -v`
Expected: All 7 tests PASS

- [ ] **Step 2: Write failing test — verify RETURNING-based ID retrieval**

Add to `tests/unit/test_clientes_crud.py`:

```python
class TestInsertClientRequestIdReliability:
    """Tests for reliable ID retrieval after insert."""

    def test_insert_returns_correct_id_for_multiple_inserts(self, db_session, seed_profiles):
        """Multiple sequential inserts should each return a unique, correct ID."""
        from database.crud.clientes import insert_client_request

        ids = []
        for i in range(5):
            rid = insert_client_request(
                db_session,
                profile_id=seed_profiles["cliente"],
                company_name=f"Company {i}",
                user_email=f"user{i}@test.com",
            )
            ids.append(rid)

        # All IDs should be unique
        assert len(set(ids)) == 5, f"Expected 5 unique IDs, got {ids}"

        # Each ID should match its company
        for i, rid in enumerate(ids):
            row = db_session.execute(
                text("SELECT company_name FROM requests WHERE id = :id"),
                {"id": rid},
            ).fetchone()
            assert row is not None, f"No row found for id={rid}"
            assert row[0] == f"Company {i}", f"ID {rid} has wrong company: {row[0]}"

    def test_insert_returns_positive_integer(self, db_session, seed_profiles):
        """Return value must be a positive integer."""
        from database.crud.clientes import insert_client_request

        rid = insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Positive ID Test",
            user_email="test@test.com",
        )
        assert isinstance(rid, int)
        assert rid > 0
```

- [ ] **Step 3: Run test to verify it passes with current code (SQLite path works)**

Run: `pytest tests/unit/test_clientes_crud.py::TestInsertClientRequestIdReliability -v`
Expected: PASS (SQLite `last_insert_rowid()` works for sequential inserts)

- [ ] **Step 4: Implement dialect-aware INSERT with RETURNING**

Replace `insert_client_request` in `database/crud/clientes.py` (lines 16-86):

```python
def insert_client_request(
    session: Session,
    profile_id: int,
    company_name: str = None,
    email: str = None,
    trading: str = None,
    location: str = None,
    language: str = None,
    reminder_frequency: str = None,
    operation_type: str = None,
    commodity: str = None,
    customs_req: str = None,
    has_customs: bool = False,
    has_port: bool = False,
    has_shipping_line: bool = False,
    requested_by: str = None,
    requested_by_type: str = None,
    user_email: str = None,
) -> int:
    """Insert a new client/provider request and return the new row id.

    Uses INSERT ... RETURNING on PostgreSQL for race-condition-safe ID
    retrieval. Falls back to last_insert_rowid() on SQLite (test env).
    """
    params = {
        "profile_id": profile_id,
        "commercial": requested_by,
        "company_name": company_name,
        "trading": trading,
        "country": location,
        "language": language,
        "email": email,
        "reminder_frequency": reminder_frequency,
        "operation_type": operation_type,
        "commodity": commodity,
        "customs_req": customs_req,
        "has_customs": has_customs,
        "has_port": has_port,
        "has_shipping_line": has_shipping_line,
        "user_email": user_email,
    }

    dialect = session.bind.dialect.name if session.bind else "unknown"

    if dialect == "postgresql":
        result = session.execute(
            text("""
                INSERT INTO requests (
                    profile_id, commercial, company_name, trading, country,
                    language, email, reminder_frequency, operation_type,
                    commodity, customs_req, has_customs, has_port,
                    has_shipping_line, user_email
                )
                VALUES (
                    :profile_id, :commercial, :company_name, :trading, :country,
                    :language, :email, :reminder_frequency, :operation_type,
                    :commodity, :customs_req, :has_customs, :has_port,
                    :has_shipping_line, :user_email
                )
                RETURNING id
            """),
            params,
        )
        request_id = result.scalar()
    else:
        # SQLite path (used in tests)
        session.execute(
            text("""
                INSERT INTO requests (
                    profile_id, commercial, company_name, trading, country,
                    language, email, reminder_frequency, operation_type,
                    commodity, customs_req, has_customs, has_port,
                    has_shipping_line, user_email
                )
                VALUES (
                    :profile_id, :commercial, :company_name, :trading, :country,
                    :language, :email, :reminder_frequency, :operation_type,
                    :commodity, :customs_req, :has_customs, :has_port,
                    :has_shipping_line, :user_email
                )
            """),
            params,
        )
        request_id = session.execute(
            text("SELECT id FROM requests WHERE rowid = last_insert_rowid()")
        ).scalar()

    session.commit()
    return request_id
```

- [ ] **Step 5: Run all clientes tests to verify no regressions**

Run: `pytest tests/unit/test_clientes_crud.py -v`
Expected: All tests PASS (including new ones)

- [ ] **Step 6: Commit**

```bash
git add database/crud/clientes.py tests/unit/test_clientes_crud.py
git commit -m "fix(crud): use RETURNING for race-safe ID retrieval (B2)"
```

---

## Task 3: Add Database Indexes

**Files:**
- Modify: `init_db.sql` (append at end)

- [ ] **Step 1: Add indexes to init_db.sql**

Append before the relationship comments section:

```sql
-- =====================
-- INDEXES
-- =====================
CREATE INDEX IF NOT EXISTS idx_requests_user_email ON requests(user_email);
CREATE INDEX IF NOT EXISTS idx_requests_company_name ON requests(company_name);
CREATE INDEX IF NOT EXISTS idx_requests_profile_id ON requests(profile_id);
CREATE INDEX IF NOT EXISTS idx_registration_request_id ON registration(request_id);
CREATE INDEX IF NOT EXISTS idx_customs_registration_request_id ON customs_registration(request_id);
CREATE INDEX IF NOT EXISTS idx_port_registration_request_id ON port_registration(request_id);
CREATE INDEX IF NOT EXISTS idx_shipping_line_registration_request_id ON shipping_line_registration(request_id);
CREATE INDEX IF NOT EXISTS idx_internal_registration_request_id ON internal_registration(request_id);
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: All tests PASS (SQLite handles CREATE INDEX IF NOT EXISTS)

- [ ] **Step 3: Commit**

```bash
git add init_db.sql
git commit -m "perf(schema): add indexes on frequently-queried columns (B3)"
```

---

# PHASE 1 — Agent Quality

## Task 4: Extract Magic Strings to `config/constants.py`

**Files:**
- Create: `config/constants.py`
- Test: `tests/unit/test_constants.py`

- [ ] **Step 1: Create config/constants.py with all extracted values**

```python
"""Centralized constants for the compliance platform.

All magic strings and hardcoded values extracted from form files.
Single source of truth for UI options and business data.
"""

# Commercial contacts
COMERCIALES = [
    "Pedro Luis Bruges",
    "Andres Consuegra",
    "Ivan Zuluaga",
    "Sharon Zuniga",
    "Johnny Farah",
    "Felipe Hoyos",
    "Jorge Sanchez",
    "Irina Paternina",
    "Stephanie Bruges",
]

# Port/terminal mappings (complete)
TERMINALES = {
    "Buenaventura": ["TCBUEN", "AGUA DULCE", "SPRBUN"],
    "Cartagena": ["COMPAS", "CONTECAR/SPRC"],
}

# Trading entity countries
TRADING_COUNTRIES = [
    "Colombia",
    "Mexico",
    "Panama",
    "Estados Unidos",
    "Chile",
    "Ecuador",
    "Peru",
    "Hong Kong",
]

# Reminder frequency options
REMINDER_FREQUENCIES = [
    "Una vez por semana",
    "Dos veces por semana",
    "Tres veces por semana",
]

# Operation types
OPERATION_TYPES = ["EXPO", "IMPO"]

# Customs systems
CUSTOMS_SYSTEMS = [
    "CARGOFLASH",
    "SIAP",
    "MOVIADUANA",
    "ITBF - USA",
    "GOMSA - MEX",
]

# Shipping line names
SHIPPING_LINES = ["MSC", "ONE", "Otro"]

# Internal document type labels (for upload form)
INTERNAL_DOC_LABELS = ["empresa", "vinculacion", "seguridad"]

# Document type ID mappings by profile ID
# Maps profile_id -> {label -> doc_type_id}
DOC_TYPE_MAPPINGS = {
    1: {"empresa": 1, "vinculacion": 2, "seguridad": 3},
    2: {"empresa": 4, "vinculacion": 5, "seguridad": 6},
}

# Maximum file size for uploads (bytes) — 10 MB
MAX_UPLOAD_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_FILE_SIZE_MB = 10

# Default pagination
DEFAULT_PAGE_SIZE = 20
```

- [ ] **Step 2: Write test to verify constants are importable and have expected types**

Create `tests/unit/test_constants.py`:

```python
"""Tests for config/constants.py — verify all constants are defined and typed."""


class TestConstants:
    def test_comerciales_is_nonempty_list(self):
        from config.constants import COMERCIALES
        assert isinstance(COMERCIALES, list)
        assert len(COMERCIALES) >= 7

    def test_terminales_has_known_ports(self):
        from config.constants import TERMINALES
        assert "Buenaventura" in TERMINALES
        assert "Cartagena" in TERMINALES
        assert isinstance(TERMINALES["Buenaventura"], list)

    def test_trading_countries_is_list(self):
        from config.constants import TRADING_COUNTRIES
        assert isinstance(TRADING_COUNTRIES, list)
        assert "Colombia" in TRADING_COUNTRIES

    def test_doc_type_mappings_has_profiles(self):
        from config.constants import DOC_TYPE_MAPPINGS
        assert 1 in DOC_TYPE_MAPPINGS
        assert 2 in DOC_TYPE_MAPPINGS
        assert "empresa" in DOC_TYPE_MAPPINGS[1]

    def test_max_upload_size(self):
        from config.constants import MAX_UPLOAD_FILE_SIZE_BYTES
        assert MAX_UPLOAD_FILE_SIZE_BYTES == 10 * 1024 * 1024
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_constants.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add config/constants.py tests/unit/test_constants.py
git commit -m "refactor: extract magic strings to config/constants.py (B14)"
```

---

## Task 5: Create Session Context Manager

**Files:**
- Create: `utils/session_helpers.py`
- Test: `tests/unit/test_session_helpers.py`

- [ ] **Step 1: Create utils/session_helpers.py**

```python
"""Session lifecycle utilities for safe database access."""
from contextlib import contextmanager
from database.db import SessionLocal


@contextmanager
def get_session():
    """Provide a transactional session that auto-closes.

    Usage:
        with get_session() as session:
            data = session.execute(...)
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 2: Write test**

Create `tests/unit/test_session_helpers.py`:

```python
"""Tests for utils/session_helpers.py."""
from unittest.mock import patch, MagicMock


class TestGetSession:
    @patch("utils.session_helpers.SessionLocal")
    def test_yields_session_and_closes(self, mock_session_local):
        from utils.session_helpers import get_session

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        with get_session() as session:
            assert session is mock_session

        mock_session.close.assert_called_once()

    @patch("utils.session_helpers.SessionLocal")
    def test_closes_session_on_exception(self, mock_session_local):
        from utils.session_helpers import get_session
        import pytest

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        with pytest.raises(ValueError):
            with get_session() as session:
                raise ValueError("test error")

        mock_session.close.assert_called_once()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_session_helpers.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add utils/session_helpers.py tests/unit/test_session_helpers.py
git commit -m "refactor: add session context manager (B13)"
```

---

## Task 6: Create Shared Form Helpers

**Files:**
- Create: `utils/form_helpers.py`
- Test: `tests/unit/test_form_helpers.py`

- [ ] **Step 1: Create utils/form_helpers.py with cached wrappers and shared patterns**

```python
"""Shared form patterns — cached data wrappers and reusable UI components."""
from __future__ import annotations

import streamlit as st
from database.db import SessionLocal
from database.crud.documents import (
    get_all_company_names,
    get_profiles_list,
    get_all_statuses,
    get_profile_id_by_name,
)


@st.cache_data(ttl=60)
def cached_company_names() -> list[str]:
    """Return company names, cached for 60 seconds."""
    session = SessionLocal()
    try:
        return get_all_company_names(session)
    finally:
        session.close()


@st.cache_data(ttl=60)
def cached_profiles_list() -> list[str]:
    """Return profile names, cached for 60 seconds."""
    session = SessionLocal()
    try:
        return get_profiles_list(session)
    finally:
        session.close()


@st.cache_data(ttl=120)
def cached_statuses() -> dict[str, int]:
    """Return {status_name: status_id} dict, cached for 120 seconds."""
    session = SessionLocal()
    try:
        return get_all_statuses(session)
    finally:
        session.close()


def status_id_to_name_map() -> dict[int, str]:
    """Return {status_id: status_name} reversed map."""
    return {v: k for k, v in cached_statuses().items()}


def cached_profile_id(profile_name: str) -> int | None:
    """Return profile_id by name, using a fresh session."""
    session = SessionLocal()
    try:
        return get_profile_id_by_name(session, profile_name)
    finally:
        session.close()
```

- [ ] **Step 2: Write tests**

Create `tests/unit/test_form_helpers.py`:

```python
"""Tests for utils/form_helpers.py — cached wrappers."""
from unittest.mock import patch, MagicMock


class TestCachedCompanyNames:
    @patch("utils.form_helpers.SessionLocal")
    @patch("utils.form_helpers.get_all_company_names")
    def test_returns_company_list(self, mock_get, mock_session_local):
        # Clear Streamlit cache for this test
        from utils.form_helpers import cached_company_names
        cached_company_names.clear()

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        mock_get.return_value = ["Acme", "Beta"]

        result = cached_company_names()
        assert result == ["Acme", "Beta"]
        mock_session.close.assert_called_once()


class TestStatusIdToNameMap:
    @patch("utils.form_helpers.cached_statuses")
    def test_reverses_status_map(self, mock_cached):
        from utils.form_helpers import status_id_to_name_map

        mock_cached.return_value = {"pendiente": 1, "aprobado": 2}
        result = status_id_to_name_map()
        assert result == {1: "pendiente", 2: "aprobado"}
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_form_helpers.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add utils/form_helpers.py tests/unit/test_form_helpers.py
git commit -m "refactor: add cached form helpers and shared utilities (B13)"
```

---

## Task 7: Decompose `request_form.py`

**Files:**
- Modify: `forms/request_form.py`
- Test: Verify existing tests still pass

- [ ] **Step 1: Run existing tests as regression baseline**

Run: `pytest tests/unit/ -v`
Expected: All PASS — this is our baseline

- [ ] **Step 2: Decompose request_form.py into helper functions**

Replace `forms/request_form.py` preserving the public `forms()` API:

```python
# forms/request_form.py
"""Request creation form — client and provider onboarding."""

import streamlit as st
from database.db import SessionLocal
from database.crud.clientes import (
    get_profile_id,
    insert_client_request,
    insert_customs_registration,
    insert_port_registration,
    insert_shipping_line_registration,
)
from services.sheets_writer import save_request
from utils.validators import validate_email, sanitize_company_name
from utils.error_handlers import handle_error
from services.logging_config import get_logger
from config.constants import (
    COMERCIALES,
    TERMINALES,
    TRADING_COUNTRIES,
    REMINDER_FREQUENCIES,
    OPERATION_TYPES,
    CUSTOMS_SYSTEMS,
    SHIPPING_LINES,
)

logger = get_logger(__name__)


def _render_request_type_selector():
    """Render request type selector and return (tipo_solicitud, profile_id, session)."""
    tipo_solicitud = st.selectbox(
        "Tipo de solicitud",
        ["cliente", "proveedor"],
        format_func=lambda x: x.capitalize(),
    )

    session = SessionLocal()
    profile_id = get_profile_id(session, tipo_solicitud)

    if profile_id is None:
        st.error("El perfil seleccionado no existe en la base de datos.")
        session.close()
        return tipo_solicitud, None, None

    return tipo_solicitud, profile_id, session


def _render_requester_section(tipo_solicitud: str):
    """Render the requester/commercial input and return (requested_by, requested_by_type)."""
    if tipo_solicitud.lower() == "cliente":
        comercial = st.selectbox("Comercial", ["Otro"] + COMERCIALES)
        if comercial == "Otro":
            comercial = st.text_input("Nombre del comercial")
        return comercial, None
    else:
        requested_by = st.text_input("Solicitante")
        requested_by_type = st.selectbox("Tipo de proveedor", ["Naviera", "Puerto", "Aduana", "Otro"])
        return requested_by, requested_by_type


def _render_company_info():
    """Render company info fields and return dict of values."""
    col1, col2, col3 = st.columns(3)
    with col1:
        company_name = st.text_input("Nombre de la compania")
        language = st.selectbox("Idioma", ["Espanol", "Ingles"])
        commodity = st.text_input("Commodity")
    with col2:
        trading = st.selectbox("Cuenta Trading", TRADING_COUNTRIES)
        email = st.text_input("Correo electronico")
    with col3:
        location = st.text_input("Pais / Ubicacion")
        reminder_frequency = st.selectbox("Frecuencia de recordatorio", REMINDER_FREQUENCIES)

    return {
        "company_name": company_name,
        "language": language,
        "commodity": commodity,
        "trading": trading,
        "email": email,
        "location": location,
        "reminder_frequency": reminder_frequency,
    }


def _render_client_specifics():
    """Render client-specific fields (operation, customs, ports, shipping lines).

    Returns dict with operation_type, customs data, port data, shipping line data.
    """
    result = {
        "operation_type": None,
        "has_customs": False,
        "has_port": False,
        "has_shipping_line": False,
        "customs_list": [],
        "ports_dict": {},
        "lines_data": {},
    }

    col4, col5 = st.columns(2)
    with col4:
        result["operation_type"] = st.selectbox("Tipo de operacion", OPERATION_TYPES)
    with col5:
        pass

    aduana = st.checkbox("Requiere registro de aduanas")
    if aduana:
        result["has_customs"] = True
        result["customs_list"] = st.multiselect("Sistemas de aduana", CUSTOMS_SYSTEMS)

    tipo_linea = st.multiselect("Linea naviera", SHIPPING_LINES)
    if tipo_linea:
        result["has_shipping_line"] = True
        for line in tipo_linea:
            line_info = {}
            if line == "MSC":
                st.markdown(f"#### Detalles de {line}")
                c1, c2 = st.columns(2)
                with c1:
                    line_info["POL"] = st.text_input(f"POL ({line})")
                    line_info["Producto"] = st.text_input(f"Producto ({line})")
                    line_info["Shipper en BL"] = st.text_input(f"Shipper en BL ({line})")
                with c2:
                    line_info["POD"] = st.text_input(f"POD ({line})")
                    line_info["Tipo de Contenedor"] = st.text_input(f"Tipo de Contenedor ({line})")
            result["lines_data"][line] = line_info

    puerto = st.checkbox("Requiere registro de puertos")
    if puerto:
        result["has_port"] = True
        selected_ports = st.multiselect("Puertos", list(TERMINALES.keys()))
        for port in selected_ports:
            terminals = st.multiselect(f"Terminales de {port}", TERMINALES.get(port, []))
            result["ports_dict"][port] = terminals

    return result


def _validate_form(company_name: str, email: str, tipo_solicitud: str, requested_by: str) -> bool:
    """Validate form inputs. Returns True if valid."""
    clean_name = sanitize_company_name(company_name)
    if not clean_name:
        st.warning("Debes ingresar el nombre de la compania.")
        return False

    if email and not validate_email(email):
        st.warning("El correo electronico no parece valido.")
        return False

    if tipo_solicitud.lower() == "proveedor" and not requested_by:
        st.warning("Debes ingresar el nombre del solicitante.")
        return False

    return True


def _save_request_to_db(session, profile_id, company_info, requested_by, requested_by_type,
                        client_data, user_email):
    """Persist request to database and Google Sheets."""
    with st.spinner("Guardando solicitud..."):
        request_id = insert_client_request(
            session,
            profile_id=profile_id,
            company_name=sanitize_company_name(company_info["company_name"]),
            email=company_info["email"],
            trading=company_info["trading"],
            location=company_info["location"],
            language=company_info["language"],
            reminder_frequency=company_info["reminder_frequency"],
            operation_type=client_data.get("operation_type"),
            commodity=company_info["commodity"],
            has_customs=client_data.get("has_customs", False),
            has_port=client_data.get("has_port", False),
            has_shipping_line=client_data.get("has_shipping_line", False),
            requested_by=requested_by,
            requested_by_type=requested_by_type,
            user_email=user_email,
        )

        if client_data.get("customs_list"):
            insert_customs_registration(session, request_id, client_data["customs_list"])

        if client_data.get("ports_dict"):
            insert_port_registration(session, request_id, client_data["ports_dict"])

        if client_data.get("lines_data"):
            insert_shipping_line_registration(session, request_id, client_data["lines_data"])

    return request_id


def _save_to_sheets(tipo_solicitud, company_info, requested_by, client_data):
    """Sync request to Google Sheets."""
    try:
        request_info = {
            "tipo_solicitud": tipo_solicitud,
            "company_name": company_info["company_name"],
            "email": company_info["email"],
            "trading": company_info["trading"],
            "location": company_info["location"],
            "language": company_info["language"],
            "reminder_frequency": company_info["reminder_frequency"],
            "tipo_operacion": client_data.get("operation_type", ""),
            "commodity": company_info["commodity"],
            "requested_by": requested_by,
            "aduana": ", ".join(client_data.get("customs_list", [])),
            "puerto": ", ".join(client_data.get("ports_dict", {}).keys()),
            "linea_naviera": ", ".join(client_data.get("lines_data", {}).keys()),
        }
        save_request(request_info)
    except Exception as e:
        logger.warning(f"Failed to sync to Google Sheets: {e}")


def forms():
    """Main request creation form — public API, unchanged."""
    st.subheader("Solicitud de Creacion de Cliente/Proveedor")

    tipo_solicitud, profile_id, session = _render_request_type_selector()
    if profile_id is None:
        return

    try:
        requested_by, requested_by_type = _render_requester_section(tipo_solicitud)
        company_info = _render_company_info()

        client_data = {}
        if tipo_solicitud.lower() == "cliente":
            client_data = _render_client_specifics()

        user_email = ""
        try:
            user_email = st.user.email if hasattr(st, "user") and st.user else ""
        except Exception:
            pass

        if st.button("Guardar solicitud"):
            if not _validate_form(company_info["company_name"], company_info["email"],
                                  tipo_solicitud, requested_by):
                return

            try:
                _save_request_to_db(
                    session, profile_id, company_info, requested_by,
                    requested_by_type, client_data, user_email,
                )
                _save_to_sheets(tipo_solicitud, company_info, requested_by, client_data)
                st.success("Solicitud guardada correctamente.")
            except Exception as e:
                session.rollback()
                handle_error(e, "Error al guardar la solicitud.")
    finally:
        session.close()
```

- [ ] **Step 3: Run full test suite to verify no regressions**

Run: `pytest tests/unit/ -v`
Expected: All tests PASS. Public API `forms()` unchanged.

- [ ] **Step 4: Commit**

```bash
git add forms/request_form.py
git commit -m "refactor: decompose request_form.py into focused helpers (B12)"
```

---

## Task 8: Decompose `upload_documents_form.py`

**Files:**
- Modify: `forms/upload_documents_form.py`

This is the largest file (529 lines). Decompose into focused helper functions while preserving the public `forms()` API. The full decomposition follows the same pattern as Task 7 — extract `_render_*` and `_save_*` helpers.

- [ ] **Step 1: Run existing tests as regression baseline**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Decompose the form function**

Key extractions:
1. `_render_company_profile_selector(session)` — lines 114-143 (company/profile selection)
2. `_render_base_data(request_id, session)` — lines 173-192 (razon_social, fecha)
3. `_render_internal_docs(profile_id, request_id)` — lines 199-259 (internal document uploads)
4. `_render_required_docs(session, profile_id, request_id)` — lines 263-361 (required doc uploads + statuses)
5. `_render_followup_section(request_id, session)` — lines 364-382 (comments/notifications)
6. `_save_all_data(session, request_id, ...)` — lines 387-527 (Drive upload + DB save)
7. `_upload_files_to_drive(uploaded_buffers, company_name, entity_type)` — lines 420-472 (Drive upload loop)
8. `_save_statuses(session, request_id, lines, ports, customs)` — lines 484-517 (status persistence)

Use `config.constants.DOC_TYPE_MAPPINGS` instead of the duplicated hardcoded dict (was at lines 215-219 and 412-415).

Each helper stays in `upload_documents_form.py` as private functions. The public API `forms()` calls them in sequence, staying under 60 lines.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 4: Run lint**

Run: `ruff check forms/upload_documents_form.py`
Expected: No violations

- [ ] **Step 5: Commit**

```bash
git add forms/upload_documents_form.py
git commit -m "refactor: decompose upload_documents_form.py into helpers (B12)"
```

---

# PHASE 2 — Agent Performance

> **Prerequisite:** Phase 1 must be complete. Agent Performance works on decomposed form files.

## Task 9: Batch Status Upsert Operations

**Files:**
- Modify: `database/crud/documents.py`
- Test: `tests/unit/test_upsert_status.py`

- [ ] **Step 1: Write regression test — existing upsert_status behavior preserved**

Run: `pytest tests/unit/test_upsert_status.py -v`
Expected: All 7 tests PASS — this is our baseline

- [ ] **Step 2: Add batch_upsert_statuses function to documents.py**

Add to `database/crud/documents.py`:

```python
def batch_upsert_statuses(
    session: Session,
    updates: list[dict],
) -> None:
    """Batch upsert status updates in a single transaction.

    Each item in `updates` must have:
        - table_name: str (e.g., "shipping_line_registration")
        - request_id: int
        - entity_name: str
        - status_id: int
        - terminal_name: str | None (only for port_registration)
    """
    for item in updates:
        upsert_status(
            session=session,
            table_name=item["table_name"],
            request_id=item["request_id"],
            entity_name=item["entity_name"],
            status_id=item["status_id"],
            terminal_name=item.get("terminal_name"),
        )
```

- [ ] **Step 3: Write test for batch function**

Add to `tests/unit/test_upsert_status.py`:

```python
class TestBatchUpsertStatuses:
    def test_batch_upsert_multiple_tables(self, db_session, seed_statuses):
        from database.crud.documents import batch_upsert_statuses

        # Create a request first
        db_session.execute(
            text("INSERT INTO profiles (name) VALUES ('cliente')")
        )
        db_session.commit()
        db_session.execute(
            text("INSERT INTO requests (profile_id, company_name) VALUES (1, 'Batch Test')")
        )
        db_session.commit()
        request_id = db_session.execute(
            text("SELECT id FROM requests WHERE company_name = 'Batch Test'")
        ).scalar()

        pending_id = seed_statuses["pendiente"]

        updates = [
            {"table_name": "shipping_line_registration", "request_id": request_id,
             "entity_name": "MSC", "status_id": pending_id},
            {"table_name": "customs_registration", "request_id": request_id,
             "entity_name": "CARGOFLASH", "status_id": pending_id},
            {"table_name": "port_registration", "request_id": request_id,
             "entity_name": "Cartagena", "status_id": pending_id, "terminal_name": "COMPAS"},
        ]

        batch_upsert_statuses(db_session, updates)
        db_session.commit()

        # Verify all 3 records created
        ship = db_session.execute(
            text("SELECT COUNT(*) FROM shipping_line_registration WHERE request_id = :rid"),
            {"rid": request_id}
        ).scalar()
        assert ship == 1

        cust = db_session.execute(
            text("SELECT COUNT(*) FROM customs_registration WHERE request_id = :rid"),
            {"rid": request_id}
        ).scalar()
        assert cust == 1

        port = db_session.execute(
            text("SELECT COUNT(*) FROM port_registration WHERE request_id = :rid"),
            {"rid": request_id}
        ).scalar()
        assert port == 1
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_upsert_status.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add database/crud/documents.py tests/unit/test_upsert_status.py
git commit -m "perf: add batch_upsert_statuses for N+1 elimination (B4)"
```

---

## Task 10: Add Caching to Form Data Fetches

**Files:**
- Modify: `forms/upload_documents_form.py` (use cached helpers)
- Modify: `forms/view_progress.py` (use cached helpers)

- [ ] **Step 1: Update upload_documents_form.py to use cached wrappers**

Replace direct `get_all_company_names(session)` and `get_profiles_list(session)` calls with:

```python
from utils.form_helpers import cached_company_names, cached_profiles_list
# ...
companies = cached_company_names()
profiles = cached_profiles_list()
```

- [ ] **Step 2: Update view_progress.py to use cached wrappers**

Replace `get_profiles_list(session)` and status map generation with:

```python
from utils.form_helpers import cached_profiles_list, status_id_to_name_map, cached_profile_id
# ...
all_profile_names = cached_profiles_list()
status_map = status_id_to_name_map()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add forms/upload_documents_form.py forms/view_progress.py
git commit -m "perf: use cached data wrappers for repeated queries (B5)"
```

---

## Task 11: Add Pagination to Progress View

**Files:**
- Modify: `database/crud/documents.py` (add pagination to `get_requests_for_progress`)
- Modify: `forms/view_progress.py` (add pagination UI)
- Test: `tests/unit/test_view_progress.py`

- [ ] **Step 1: Add pagination parameters to get_requests_for_progress**

Modify in `database/crud/documents.py`:

```python
def get_requests_for_progress(
    session: Session,
    only_for_email: str | None = None,
    page: int = 0,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """Return paginated requests and total count.

    Returns: (list_of_request_dicts, total_count)
    """
    count_sql = text("""
        SELECT COUNT(*)
        FROM requests
        WHERE (:email IS NULL OR LOWER(user_email) = LOWER(:email))
    """)
    total = session.execute(count_sql, {"email": only_for_email}).scalar()

    sql = text("""
        SELECT id, company_name, profile_id, created_at, user_email
        FROM requests
        WHERE (:email IS NULL OR LOWER(user_email) = LOWER(:email))
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = session.execute(sql, {
        "email": only_for_email,
        "limit": page_size,
        "offset": page * page_size,
    }).fetchall()

    results = [
        {
            "id": r.id,
            "company_name": r.company_name,
            "profile_id": r.profile_id,
            "created_at": r.created_at,
            "user_email": r.user_email,
        }
        for r in rows
    ]
    return results, total
```

- [ ] **Step 2: Write test for pagination**

Add to `tests/unit/test_view_progress.py`:

```python
class TestProgressPagination:
    def test_get_requests_for_progress_pagination(self, db_session, seed_profiles):
        from database.crud.documents import get_requests_for_progress

        # Insert 5 requests
        for i in range(5):
            db_session.execute(
                text("INSERT INTO requests (profile_id, company_name, user_email) VALUES (:pid, :name, :email)"),
                {"pid": seed_profiles["cliente"], "name": f"Co {i}", "email": "test@test.com"}
            )
        db_session.commit()

        # Page 0 with size 2
        results, total = get_requests_for_progress(db_session, page=0, page_size=2)
        assert total == 5
        assert len(results) == 2

        # Page 2 with size 2 (last page, only 1 result)
        results, total = get_requests_for_progress(db_session, page=2, page_size=2)
        assert total == 5
        assert len(results) == 1
```

- [ ] **Step 3: Add pagination UI to view_progress.py**

Add pagination controls after the filter section:

```python
# In show_progress_view(), after email_filter:
from config.constants import DEFAULT_PAGE_SIZE

page_key = "progress_page"
if page_key not in st.session_state:
    st.session_state[page_key] = 0

requests, total_count = get_requests_for_progress(
    session,
    only_for_email=email_filter,
    page=st.session_state[page_key],
    page_size=DEFAULT_PAGE_SIZE,
)

# ... existing display logic ...

# Pagination controls at bottom
total_pages = max(1, (total_count + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE)
col_prev, col_info, col_next = st.columns([1, 2, 1])
with col_prev:
    if st.button("< Anterior", disabled=st.session_state[page_key] == 0):
        st.session_state[page_key] -= 1
        st.rerun()
with col_info:
    st.caption(f"Pagina {st.session_state[page_key] + 1} de {total_pages} ({total_count} solicitudes)")
with col_next:
    if st.button("Siguiente >", disabled=st.session_state[page_key] >= total_pages - 1):
        st.session_state[page_key] += 1
        st.rerun()
```

- [ ] **Step 4: Update existing callers of get_requests_for_progress**

Any other code calling `get_requests_for_progress()` must now handle the tuple return `(results, total)`. Check and update.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add database/crud/documents.py forms/view_progress.py tests/unit/test_view_progress.py
git commit -m "perf: add pagination to progress view (B6)"
```

---

# PHASE 2 — Agent Validation

> **Prerequisite:** Phase 1 must be complete. Agent Validation works on decomposed form files.

## Task 12: Add Loading States

**Files:**
- Modify: `forms/request_form.py` (already has `st.spinner` from Task 7)
- Modify: `forms/upload_documents_form.py`

- [ ] **Step 1: Add st.spinner to upload_documents_form save operations**

In the decomposed `_save_all_data()` function, wrap the Drive upload and DB save sections:

```python
with st.spinner("Subiendo documentos a Google Drive..."):
    _upload_files_to_drive(...)

with st.spinner("Guardando datos en la base de datos..."):
    _save_statuses(...)
    session.commit()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add forms/upload_documents_form.py
git commit -m "ux: add loading spinners to save operations (B7)"
```

---

## Task 13: Improve Error Handling

**Files:**
- Modify: `forms/request_form.py` (already improved in Task 7)
- Modify: `forms/upload_documents_form.py`
- Test: `tests/unit/test_error_handling.py`

- [ ] **Step 1: Run existing error handling tests as baseline**

Run: `pytest tests/unit/test_error_handling.py -v`
Expected: All PASS

- [ ] **Step 2: Replace bare except blocks in upload_documents_form.py**

In the decomposed save functions, replace generic `except Exception` with specific types:

```python
from utils.exceptions import DatabaseError, DriveUploadError, ValidationError

# In _upload_files_to_drive():
try:
    link = upload_to_drive(service, folder_id, tmp_file.name, safe_name)
except Exception as e:
    logger.exception(f"Drive upload failed for {safe_name}")
    raise DriveUploadError(f"Error subiendo {safe_name}", file_name=safe_name) from e

# In _save_all_data():
try:
    _upload_files_to_drive(...)
    _save_statuses(...)
    session.commit()
    st.success("Datos guardados correctamente.")
except DriveUploadError as e:
    session.rollback()
    handle_error(e, f"Error al subir archivo: {e.file_name}")
except DatabaseError as e:
    session.rollback()
    handle_error(e, "Error al guardar en la base de datos.")
except Exception as e:
    session.rollback()
    logger.exception("Unexpected error in save")
    handle_error(e, "Error inesperado al guardar los datos.")
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add forms/upload_documents_form.py
git commit -m "fix: replace bare except blocks with specific error handling (B8, B9)"
```

---

## Task 14: Add Input Validations

**Files:**
- Modify: `forms/upload_documents_form.py`
- Modify: `forms/request_form.py` (already has validation from Task 7)
- Test: `tests/unit/test_validators.py`

- [ ] **Step 1: Add file size validation to validators**

Add to `utils/validators.py`:

```python
from config.constants import MAX_UPLOAD_FILE_SIZE_BYTES, MAX_UPLOAD_FILE_SIZE_MB


def validate_file_size(uploaded_file) -> bool:
    """Check that a Streamlit UploadedFile is within size limits."""
    if uploaded_file is None:
        return True
    return uploaded_file.size <= MAX_UPLOAD_FILE_SIZE_BYTES


def file_size_error_message() -> str:
    return f"El archivo excede el tamano maximo permitido ({MAX_UPLOAD_FILE_SIZE_MB} MB)."
```

- [ ] **Step 2: Write test for file size validation**

Add to `tests/unit/test_validators.py`:

```python
class TestFileValidation:
    def test_validate_file_size_under_limit(self):
        from utils.validators import validate_file_size
        from unittest.mock import MagicMock

        mock_file = MagicMock()
        mock_file.size = 5 * 1024 * 1024  # 5 MB
        assert validate_file_size(mock_file) is True

    def test_validate_file_size_over_limit(self):
        from utils.validators import validate_file_size
        from unittest.mock import MagicMock

        mock_file = MagicMock()
        mock_file.size = 15 * 1024 * 1024  # 15 MB
        assert validate_file_size(mock_file) is False

    def test_validate_file_size_none(self):
        from utils.validators import validate_file_size
        assert validate_file_size(None) is True
```

- [ ] **Step 3: Add file size check to upload_documents_form.py**

In the decomposed `_upload_files_to_drive()` function, before uploading:

```python
from utils.validators import validate_file_size, file_size_error_message

for file in files:
    if not validate_file_size(file):
        st.warning(f"{file.name}: {file_size_error_message()}")
        continue
    # ... proceed with upload
```

- [ ] **Step 4: Add empty selection validation to request_form.py**

Already handled in `_validate_form()` from Task 7. Verify the validation covers empty company name and invalid email.

- [ ] **Step 5: Run all tests**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add utils/validators.py forms/upload_documents_form.py tests/unit/test_validators.py
git commit -m "feat: add file size and input validations (B10, B11)"
```

---

# PHASE 3 — Integration Verification

## Task 15: Full Verification

- [ ] **Step 1: Run complete test suite**

```bash
pytest tests/unit/ -v --tb=short
```
Expected: All tests PASS

- [ ] **Step 2: Run coverage check**

```bash
pytest tests/unit/ --cov=. --cov-report=term-missing
```
Expected: No coverage regression

- [ ] **Step 3: Run linter**

```bash
ruff check .
```
Expected: No violations (or only pre-existing ones)

- [ ] **Step 4: Run type checker**

```bash
mypy . --ignore-missing-imports
```
Expected: No new errors

- [ ] **Step 5: Verify file structure**

Confirm these new files exist:
- `config/constants.py`
- `utils/session_helpers.py`
- `utils/form_helpers.py`

Confirm these files were modified (not deleted):
- `init_db.sql`
- `database/crud/clientes.py`
- `database/crud/documents.py`
- `forms/request_form.py`
- `forms/upload_documents_form.py`
- `forms/view_progress.py`
- `utils/validators.py`

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: SP1 complete — bugs fixed + robustness improvements"
```
