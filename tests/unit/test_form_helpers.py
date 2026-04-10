"""Tests for utils/form_helpers.py -- cached wrappers."""
import sys
import types
from unittest.mock import MagicMock, patch

# Stub database.db before importing form_helpers so the module-level
# DATABASE_URL resolution (which reads st.secrets) does not fire.
_db_stub = types.ModuleType("database.db")
_db_stub.SessionLocal = MagicMock
sys.modules.setdefault("database.db", _db_stub)

from utils.form_helpers import (  # noqa: E402
    cached_company_names,
    cached_profiles_list,
    cached_statuses,
    status_id_to_name_map,
    cached_profile_id,
)


class TestCachedCompanyNames:
    def test_returns_company_list(self):
        mock_session = MagicMock()
        mock_session_cls = MagicMock(return_value=mock_session)

        with patch("utils.form_helpers.SessionLocal", mock_session_cls), \
             patch("utils.form_helpers.get_all_company_names", return_value=["Acme", "Beta"]):
            cached_company_names.clear()
            result = cached_company_names()
            assert result == ["Acme", "Beta"]
            mock_session.close.assert_called_once()

    def test_returns_empty_list(self):
        mock_session = MagicMock()
        mock_session_cls = MagicMock(return_value=mock_session)

        with patch("utils.form_helpers.SessionLocal", mock_session_cls), \
             patch("utils.form_helpers.get_all_company_names", return_value=[]):
            cached_company_names.clear()
            result = cached_company_names()
            assert result == []
            mock_session.close.assert_called_once()


class TestCachedProfilesList:
    def test_returns_profiles(self):
        mock_session = MagicMock()
        mock_session_cls = MagicMock(return_value=mock_session)

        with patch("utils.form_helpers.SessionLocal", mock_session_cls), \
             patch("utils.form_helpers.get_profiles_list", return_value=["cliente", "proveedor"]):
            cached_profiles_list.clear()
            result = cached_profiles_list()
            assert result == ["cliente", "proveedor"]
            mock_session.close.assert_called_once()


class TestCachedStatuses:
    def test_returns_status_dict(self):
        mock_session = MagicMock()
        mock_session_cls = MagicMock(return_value=mock_session)

        with patch("utils.form_helpers.SessionLocal", mock_session_cls), \
             patch("utils.form_helpers.get_all_statuses", return_value={"pendiente": 1, "aprobado": 2}):
            cached_statuses.clear()
            result = cached_statuses()
            assert result == {"pendiente": 1, "aprobado": 2}
            mock_session.close.assert_called_once()


class TestStatusIdToNameMap:
    def test_reverses_status_map(self):
        with patch("utils.form_helpers.cached_statuses", return_value={"pendiente": 1, "aprobado": 2}):
            result = status_id_to_name_map()
            assert result == {1: "pendiente", 2: "aprobado"}

    def test_empty_map(self):
        with patch("utils.form_helpers.cached_statuses", return_value={}):
            result = status_id_to_name_map()
            assert result == {}


class TestCachedProfileId:
    def test_returns_profile_id(self):
        mock_session = MagicMock()
        mock_session_cls = MagicMock(return_value=mock_session)

        with patch("utils.form_helpers.SessionLocal", mock_session_cls), \
             patch("utils.form_helpers.get_profile_id_by_name", return_value=42):
            result = cached_profile_id("cliente")
            assert result == 42
            mock_session.close.assert_called_once()

    def test_returns_none_for_unknown(self):
        mock_session = MagicMock()
        mock_session_cls = MagicMock(return_value=mock_session)

        with patch("utils.form_helpers.SessionLocal", mock_session_cls), \
             patch("utils.form_helpers.get_profile_id_by_name", return_value=None):
            result = cached_profile_id("nonexistent")
            assert result is None
            mock_session.close.assert_called_once()
