"""
Shared pytest fixtures for the compliance-platform test suite.

IMPORTANT: This module mocks Streamlit and external services BEFORE any
application code is imported.  Module-level code in sheets_writer.py and
google_drive_utils.py calls st.secrets at import time, so the mocks must
be in place first.
"""

import types
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Schema DDL (subset of init_db.sql, adapted for SQLite)
# ---------------------------------------------------------------------------
# SQLite doesn't support SERIAL; we use INTEGER PRIMARY KEY AUTOINCREMENT.
# Foreign-key column types are simplified to INTEGER / TEXT.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS document_type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    category VARCHAR(150) NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    commercial VARCHAR(255),
    company_name VARCHAR(255),
    trading VARCHAR(100),
    country VARCHAR(100),
    language VARCHAR(50),
    email VARCHAR(255),
    reminder_frequency VARCHAR(100),
    operation_type VARCHAR(50),
    commodity VARCHAR(255),
    customs_req TEXT,
    has_customs BOOLEAN DEFAULT 0,
    has_port BOOLEAN DEFAULT 0,
    has_shipping_line BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_email VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id),
    comments TEXT,
    notifications TEXT
);

CREATE TABLE IF NOT EXISTS registration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id),
    doc_type_id INTEGER REFERENCES document_type(id),
    id_comments INTEGER REFERENCES comments(id),
    status_id INTEGER REFERENCES status(id),
    file_name VARCHAR(255),
    drive_link TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by VARCHAR(150),
    razon_social VARCHAR(255),
    fecha_creacion DATE
);

CREATE TABLE IF NOT EXISTS customs_registration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id),
    customs_name VARCHAR(150) NOT NULL,
    status_id INTEGER REFERENCES status(id)
);

CREATE TABLE IF NOT EXISTS port_registration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id),
    port_name VARCHAR(150) NOT NULL,
    terminal_name VARCHAR(150),
    status_id INTEGER REFERENCES status(id)
);

CREATE TABLE IF NOT EXISTS shipping_line_registration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id),
    line_name VARCHAR(150) NOT NULL,
    pol VARCHAR(150),
    pod VARCHAR(150),
    product VARCHAR(255),
    container_type VARCHAR(50),
    shipper_bl VARCHAR(255),
    status_id INTEGER REFERENCES status(id)
);

CREATE TABLE IF NOT EXISTS internal_registration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id),
    internal_label VARCHAR(255),
    status_id INTEGER REFERENCES status(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_email VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id INTEGER,
    old_value TEXT,
    new_value TEXT,
    details TEXT
);
"""


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine():
    """Create a disposable SQLite in-memory engine with the full schema."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    with engine.connect() as conn:
        for statement in _SCHEMA_SQL.strip().split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
        conn.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Provide a transactional SQLAlchemy session that rolls back after each test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# Seed-data helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_profiles(db_session):
    """Insert the standard profile rows (cliente, proveedor) and return a
    mapping of name -> id."""
    db_session.execute(text("INSERT INTO profiles (name) VALUES ('cliente')"))
    db_session.execute(text("INSERT INTO profiles (name) VALUES ('proveedor')"))
    db_session.commit()

    rows = db_session.execute(text("SELECT id, name FROM profiles")).fetchall()
    return {row[1]: row[0] for row in rows}


@pytest.fixture
def seed_statuses(db_session):
    """Insert common status rows and return a mapping of status -> id."""
    statuses = ["pendiente", "aprobado", "rechazado", "en revision"]
    for s in statuses:
        db_session.execute(text("INSERT INTO status (status) VALUES (:s)"), {"s": s})
    db_session.commit()

    rows = db_session.execute(text("SELECT id, status FROM status")).fetchall()
    return {row[1]: row[0] for row in rows}


# ---------------------------------------------------------------------------
# Streamlit mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_streamlit(monkeypatch):
    """Mock Streamlit components so application modules can be imported safely.

    This patches ``streamlit.secrets``, ``streamlit.session_state``, and
    ``streamlit.user`` with test-safe values.  Use this fixture whenever a
    test (or one of its imports) touches anything from Streamlit.
    """
    mock_secrets = {
        "DATABASE_URL": "sqlite:///:memory:",
        "google_drive_credentials": {
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key-id",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----\n",
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        "google_sheets_credentials": {
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key-id",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----\n",
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        "general": {"compliance_id": "test_compliance_id"},
        "drive": {
            "shared_drive_id": "test_drive",
            "parent_folder_id": "test_parent",
            "clients_folder_id": "test_clients",
            "providers_folder_id": "test_providers",
        },
    }

    # Make secrets dict-like but also support attribute access (st.secrets["key"]
    # and st.secrets.key both work in real Streamlit).
    class _MockSecrets(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError:
                raise AttributeError(name)

    secrets = _MockSecrets(mock_secrets)

    mock_session_state = {}

    mock_user = types.SimpleNamespace(
        email="test@tradingsolutions.com",
        name="Test User",
        is_logged_in=True,
    )

    monkeypatch.setattr("streamlit.secrets", secrets)
    monkeypatch.setattr("streamlit.session_state", mock_session_state)
    # st.user may not exist as a module attribute outside Streamlit Cloud,
    # so use setattr directly with raising=False to create it if absent.
    import streamlit as _st
    monkeypatch.setattr(_st, "user", mock_user, raising=False)

    return {
        "secrets": secrets,
        "session_state": mock_session_state,
        "user": mock_user,
    }


# ---------------------------------------------------------------------------
# Google Drive mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_google_drive():
    """Return a MagicMock that imitates the Google Drive v3 service object.

    The mock pre-configures the most common call chains so tests can assert
    on them without wiring up the full Google client library.
    """
    service = MagicMock()

    # files().list().execute() -> empty results by default
    service.files.return_value.list.return_value.execute.return_value = {
        "files": []
    }

    # files().create().execute() -> fake file
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "fake_file_id",
        "webViewLink": "https://drive.google.com/file/d/fake_file_id/view",
    }

    # permissions().create().execute() -> ok
    service.permissions.return_value.create.return_value.execute.return_value = {}

    return service


# ---------------------------------------------------------------------------
# Google Sheets mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_google_sheets():
    """Return a MagicMock that imitates a ``gspread.Client`` object.

    Includes a pre-built worksheet mock returned by
    ``client.open_by_key(...).worksheet(...)``.
    """
    client = MagicMock()

    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records.return_value = []
    mock_worksheet.append_row.return_value = None

    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet

    client.open_by_key.return_value = mock_spreadsheet

    return client
