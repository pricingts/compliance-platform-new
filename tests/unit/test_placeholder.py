"""Placeholder tests to verify the test infrastructure works."""

import pytest


def test_placeholder():
    """Trivial test to verify pytest runs."""
    assert True


@pytest.mark.unit
def test_unit_marker():
    """Verify the 'unit' marker works."""
    assert 1 + 1 == 2


class TestDbSessionFixture:
    """Verify that the db_session fixture provides a working SQLite session."""

    def test_session_connects(self, db_session):
        """Session should execute a basic query without errors."""
        from sqlalchemy import text

        result = db_session.execute(text("SELECT 1")).scalar()
        assert result == 1

    def test_schema_tables_exist(self, db_session):
        """All expected tables should be present after schema creation."""
        from sqlalchemy import text

        rows = db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).fetchall()
        table_names = {row[0] for row in rows}

        expected = {
            "profiles",
            "status",
            "document_type",
            "requests",
            "registration",
            "comments",
            "customs_registration",
            "port_registration",
            "shipping_line_registration",
            "internal_registration",
        }
        assert expected.issubset(table_names), (
            f"Missing tables: {expected - table_names}"
        )

    def test_insert_and_query(self, db_session):
        """Basic insert/select round-trip should work."""
        from sqlalchemy import text

        db_session.execute(text("INSERT INTO profiles (name) VALUES ('cliente')"))
        db_session.commit()

        name = db_session.execute(
            text("SELECT name FROM profiles WHERE name = 'cliente'")
        ).scalar()
        assert name == "cliente"


class TestSeedFixtures:
    """Verify seed-data fixtures."""

    def test_seed_profiles(self, db_session, seed_profiles):
        assert "cliente" in seed_profiles
        assert "proveedor" in seed_profiles
        assert isinstance(seed_profiles["cliente"], int)

    def test_seed_statuses(self, db_session, seed_statuses):
        assert "pendiente" in seed_statuses
        assert "aprobado" in seed_statuses
        assert len(seed_statuses) == 4


class TestMockFixtures:
    """Verify that mock fixtures instantiate without errors."""

    def test_mock_streamlit(self, mock_streamlit):
        assert mock_streamlit["secrets"]["DATABASE_URL"] == "sqlite:///:memory:"
        assert mock_streamlit["user"].email == "test@tradingsolutions.com"
        assert mock_streamlit["user"].is_logged_in is True
        # Attribute-style access should also work
        assert mock_streamlit["secrets"].general["compliance_id"] == "test_compliance_id"

    def test_mock_google_drive(self, mock_google_drive):
        result = mock_google_drive.files().list().execute()
        assert result == {"files": []}

        result = mock_google_drive.files().create().execute()
        assert "id" in result
        assert "webViewLink" in result

    def test_mock_google_sheets(self, mock_google_sheets):
        ws = mock_google_sheets.open_by_key("any_key").worksheet("Sheet1")
        assert ws.get_all_records() == []
        ws.append_row(["a", "b"])  # should not raise
