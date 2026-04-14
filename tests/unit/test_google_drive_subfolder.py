"""Tests for the new Drive helpers added in Phase 4:
- find_or_create_subfolder (creates 'Adjuntos Solicitud' under the company folder)
- upload_to_drive with auto-detected mimetype (fixes hardcoded PDF bug)
"""
from __future__ import annotations

from unittest.mock import MagicMock


class TestFindOrCreateSubfolder:
    def test_returns_existing_subfolder_id(self, mock_streamlit, mock_google_drive):
        from services.google_drive_utils import find_or_create_subfolder
        mock_google_drive.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "existing_subfolder_123", "name": "Adjuntos Solicitud"}],
        }
        result = find_or_create_subfolder(mock_google_drive, "parent_folder_id", "Adjuntos Solicitud")
        assert result == "existing_subfolder_123"
        # Should NOT have called create
        mock_google_drive.files.return_value.create.assert_not_called()

    def test_creates_subfolder_when_missing(self, mock_streamlit, mock_google_drive):
        from services.google_drive_utils import find_or_create_subfolder
        mock_google_drive.files.return_value.list.return_value.execute.return_value = {"files": []}
        mock_google_drive.files.return_value.create.return_value.execute.return_value = {"id": "new_sub_999"}
        result = find_or_create_subfolder(mock_google_drive, "parent_folder_id", "Adjuntos Solicitud")
        assert result == "new_sub_999"
        # Verify the create call used the correct parent
        create_call = mock_google_drive.files.return_value.create.call_args
        body = create_call.kwargs["body"]
        assert body["name"] == "Adjuntos Solicitud"
        assert body["mimeType"] == "application/vnd.google-apps.folder"
        assert body["parents"] == ["parent_folder_id"]


class TestUploadToDriveMimetype:
    def test_default_mimetype_pdf_for_pdf(self, mock_streamlit, mock_google_drive, tmp_path):
        from services.google_drive_utils import upload_to_drive
        import services.google_drive_utils as g
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        captured = {}
        original = g.MediaFileUpload
        try:
            def _spy(file_path, mimetype, resumable=True):
                captured["mimetype"] = mimetype
                return MagicMock()
            g.MediaFileUpload = _spy
            upload_to_drive(mock_google_drive, "folder", str(f), "test.pdf")
        finally:
            g.MediaFileUpload = original
        assert captured["mimetype"] == "application/pdf"

    def test_mimetype_auto_detects_docx(self, mock_streamlit, mock_google_drive, tmp_path):
        from services.google_drive_utils import upload_to_drive
        import services.google_drive_utils as g
        f = tmp_path / "test.docx"
        f.write_bytes(b"PK\x03\x04")  # docx is a zip
        captured = {}
        original = g.MediaFileUpload
        try:
            def _spy(file_path, mimetype, resumable=True):
                captured["mimetype"] = mimetype
                return MagicMock()
            g.MediaFileUpload = _spy
            upload_to_drive(mock_google_drive, "folder", str(f), "test.docx")
        finally:
            g.MediaFileUpload = original
        # Should auto-detect to docx mimetype, NOT default to PDF
        assert captured["mimetype"] != "application/pdf"
        assert "officedocument" in captured["mimetype"] or captured["mimetype"].endswith("docx")

    def test_explicit_mimetype_param_wins(self, mock_streamlit, mock_google_drive, tmp_path):
        from services.google_drive_utils import upload_to_drive
        import services.google_drive_utils as g
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\x01\x02")
        captured = {}
        original = g.MediaFileUpload
        try:
            def _spy(file_path, mimetype, resumable=True):
                captured["mimetype"] = mimetype
                return MagicMock()
            g.MediaFileUpload = _spy
            upload_to_drive(mock_google_drive, "folder", str(f), "test.bin", mimetype="image/png")
        finally:
            g.MediaFileUpload = original
        assert captured["mimetype"] == "image/png"
