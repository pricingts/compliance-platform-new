"""Tests for the Google Sheets sync feature flag in forms/request_form.py.

When ``st.secrets['sheets']['enabled']`` is falsy (or absent), the form
must NOT call ``save_request``. This keeps the legacy Apps Script
notifier silent once the Python mailer has taken over.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def _import_form(mock_streamlit):
    """Import forms.request_form with streamlit mocked — returns the module."""
    import importlib

    import forms.request_form as rf

    importlib.reload(rf)
    return rf


class TestSheetsGate:
    def test_sheets_disabled_by_default(self, mock_streamlit, _import_form):
        """Absent [sheets] section in secrets → disabled."""
        # mock_streamlit seeds secrets WITHOUT a [sheets] section.
        assert _import_form._is_sheets_enabled() is False

    def test_sheets_enabled_when_flag_true(self, mock_streamlit, _import_form):
        mock_streamlit["secrets"]["sheets"] = {"enabled": True}
        assert _import_form._is_sheets_enabled() is True

    def test_sheets_disabled_when_flag_false(self, mock_streamlit, _import_form):
        mock_streamlit["secrets"]["sheets"] = {"enabled": False}
        assert _import_form._is_sheets_enabled() is False

    def test_sheets_disabled_when_section_empty(self, mock_streamlit, _import_form):
        mock_streamlit["secrets"]["sheets"] = {}
        assert _import_form._is_sheets_enabled() is False
