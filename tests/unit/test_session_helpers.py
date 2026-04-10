"""Tests for utils/session_helpers.py."""
import sys
from unittest.mock import patch, MagicMock

import pytest


# database.db tries to resolve DATABASE_URL at import time, which fails in
# the unit-test environment.  We inject a lightweight stub so that importing
# utils.session_helpers succeeds without a live database.
_mock_db_module = MagicMock()
sys.modules.setdefault("database.db", _mock_db_module)

from utils.session_helpers import get_session  # noqa: E402


class TestGetSession:
    def test_yields_session_and_closes(self):
        mock_session = MagicMock()

        with patch("utils.session_helpers.SessionLocal", return_value=mock_session):
            with get_session() as session:
                assert session is mock_session

        mock_session.close.assert_called_once()

    def test_closes_session_on_exception(self):
        mock_session = MagicMock()

        with patch("utils.session_helpers.SessionLocal", return_value=mock_session):
            with pytest.raises(ValueError):
                with get_session() as session:
                    raise ValueError("test error")

        mock_session.close.assert_called_once()
