"""Tests for Google Sheets writer service (services/sheets_writer.py).

Bug 3: Module-level Google auth executes at import time, crashing the import
       if secrets are unavailable.  After the fix, auth should be lazy so the
       module can be imported without any Google secrets configured.
"""

import sys
from unittest.mock import MagicMock, patch



class TestSheetsWriterImport:
    """Verify that sheets_writer can be imported without live Google credentials."""

    def test_import_without_secrets_does_not_crash(self):
        """Importing sheets_writer without Google secrets should not crash.

        After the lazy-init fix the module should be importable even when
        st.secrets is missing or empty -- no Google API calls at import time.
        """
        # Remove cached module so we get a fresh import
        mod_name = "services.sheets_writer"
        saved = sys.modules.pop(mod_name, None)
        try:
            # Patch streamlit so import doesn't need real st.secrets
            with patch.dict(sys.modules, {"streamlit": MagicMock()}):
                import importlib
                mod = importlib.import_module(mod_name)
                # Module should have the public functions
                assert hasattr(mod, "get_or_create_worksheet")
                assert hasattr(mod, "save_request")
        finally:
            # Restore original module state
            if saved is not None:
                sys.modules[mod_name] = saved
            else:
                sys.modules.pop(mod_name, None)


class TestSheetsWriterFunctions:
    """Verify sheets_writer functions work correctly with mocked Google clients."""

    def test_get_or_create_worksheet_returns_existing(self, mock_streamlit, mock_google_sheets):
        """get_or_create_worksheet returns an existing worksheet when found."""
        mod_name = "services.sheets_writer"
        saved = sys.modules.pop(mod_name, None)
        try:
            import services.sheets_writer as sw
            # Inject mocked client
            sw._client = mock_google_sheets
            sw._compliance_id = "test_compliance_id"

            ws = sw.get_or_create_worksheet("TestSheet")
            assert ws is not None
            mock_google_sheets.open_by_key.assert_called_with("test_compliance_id")
        finally:
            # Reset module globals
            sw._client = None
            sw._sheets_service = None
            sw._compliance_id = None
            if saved is not None:
                sys.modules[mod_name] = saved

    def test_get_or_create_worksheet_creates_new(self, mock_streamlit, mock_google_sheets):
        """get_or_create_worksheet creates a new worksheet when WorksheetNotFound is raised."""
        import gspread

        # Make worksheet() raise WorksheetNotFound
        mock_spreadsheet = mock_google_sheets.open_by_key.return_value
        mock_spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound("NotFound")

        mock_new_ws = MagicMock()
        mock_spreadsheet.add_worksheet.return_value = mock_new_ws

        mod_name = "services.sheets_writer"
        saved = sys.modules.pop(mod_name, None)
        try:
            import services.sheets_writer as sw
            sw._client = mock_google_sheets
            sw._compliance_id = "test_compliance_id"

            headers = ["Col1", "Col2"]
            ws = sw.get_or_create_worksheet("NewSheet", headers=headers)

            assert ws is mock_new_ws
            mock_spreadsheet.add_worksheet.assert_called_once()
            mock_new_ws.append_row.assert_called_once_with(headers)
        finally:
            sw._client = None
            sw._sheets_service = None
            sw._compliance_id = None
            if saved is not None:
                sys.modules[mod_name] = saved

    def test_save_request_appends_row(self, mock_streamlit, mock_google_sheets):
        """save_request should append a row to the worksheet."""
        mod_name = "services.sheets_writer"
        saved = sys.modules.pop(mod_name, None)
        try:
            import services.sheets_writer as sw
            sw._client = mock_google_sheets
            sw._compliance_id = "test_compliance_id"

            mock_ws = mock_google_sheets.open_by_key.return_value.worksheet.return_value

            request_info = {
                "requested_by": "Juan",
                "tipo_solicitud": "Cliente",
                "company_name": "TestCorp",
                "email": "test@test.com",
                "trading": "TR001",
                "location": "Colombia",
                "language": "es",
                "reminder_frequency": "weekly",
                "tipo_operacion": "EXPO",
                "commodity": "Coffee",
                "aduana": "Si",
                "puerto": "No",
                "linea_naviera": "Si",
            }

            sw.save_request(request_info)

            mock_ws.append_row.assert_called_once()
            row_data = mock_ws.append_row.call_args[0][0]
            # First element is the date, rest are from request_info
            assert row_data[1] == "Juan"
            assert row_data[3] == "TestCorp"
            assert row_data[4] == "test@test.com"
        finally:
            sw._client = None
            sw._sheets_service = None
            sw._compliance_id = None
            if saved is not None:
                sys.modules[mod_name] = saved
