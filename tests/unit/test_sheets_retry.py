"""Tests for retry and error-propagation hardening in services/sheets_writer.

Phase 5 adds:
- @with_retry on save_request / get_or_create_worksheet. Retries on
  HttpError / OSError / gspread.exceptions.APIError / ConnectionError.
- SpreadsheetNotFound no longer renders st.error and swallows the failure —
  it raises SheetsError so callers decide how to surface it.
- UI calls (st.error / st.warning) are removed from this module.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Disable real sleep in utils.retry so tests are fast."""
    import utils.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)


def _make_api_error():
    """Build a minimal gspread.exceptions.APIError for tests."""
    import gspread
    resp = MagicMock()
    resp.status_code = 503
    resp.text = "Service Unavailable"
    resp.json.return_value = {"error": {"code": 503, "message": "unavailable"}}
    try:
        return gspread.exceptions.APIError(resp)
    except Exception:
        # Older gspread takes no arg; fall back to a plain instance.
        exc = gspread.exceptions.APIError.__new__(gspread.exceptions.APIError)
        exc.response = resp
        exc.args = ("503 Service Unavailable",)
        return exc


class TestSaveRequestRetry:
    def test_save_request_retries_on_api_error(self, mock_streamlit, mock_google_sheets):
        """APIError on the first 2 append_row calls should retry; succeed on 3rd."""
        mod_name = "services.sheets_writer"
        saved = sys.modules.pop(mod_name, None)
        try:
            import services.sheets_writer as sw
            sw._client = mock_google_sheets
            sw._compliance_id = "test_compliance_id"

            mock_ws = mock_google_sheets.open_by_key.return_value.worksheet.return_value

            attempts = {"n": 0}

            def _flaky_append(*args, **kwargs):
                attempts["n"] += 1
                if attempts["n"] < 3:
                    raise _make_api_error()
                return None

            mock_ws.append_row.side_effect = _flaky_append

            sw.save_request({"case_id": "C0100", "company_name": "RetryCo"})

            # 3 append calls (2 failures + 1 success)
            assert attempts["n"] == 3
        finally:
            sw._client = None
            sw._sheets_service = None
            sw._compliance_id = None
            if saved is not None:
                sys.modules[mod_name] = saved

    def test_get_or_create_worksheet_raises_sheets_error_on_spreadsheet_not_found(
        self, mock_streamlit, mock_google_sheets
    ):
        """When the spreadsheet key is wrong, the module raises SheetsError (not st.error)."""
        import gspread

        from utils.exceptions import SheetsError

        mock_google_sheets.open_by_key.side_effect = gspread.exceptions.SpreadsheetNotFound("nope")

        mod_name = "services.sheets_writer"
        saved = sys.modules.pop(mod_name, None)
        try:
            import services.sheets_writer as sw
            sw._client = mock_google_sheets
            sw._compliance_id = "test_compliance_id"

            with pytest.raises(SheetsError):
                sw.get_or_create_worksheet("AnySheet")
        finally:
            sw._client = None
            sw._sheets_service = None
            sw._compliance_id = None
            if saved is not None:
                sys.modules[mod_name] = saved
