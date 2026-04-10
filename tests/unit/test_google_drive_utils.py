"""Tests for Google Drive utilities - security focused."""
import pytest
from unittest.mock import MagicMock, patch, call


class TestUploadToDrive:
    """Tests for the upload_to_drive function."""

    def test_upload_does_not_create_public_permission(self, mock_google_drive):
        """Upload should NOT create 'anyone' permission (security fix)."""
        with patch("services.google_drive_utils.MediaFileUpload"):
            from services.google_drive_utils import upload_to_drive

            upload_to_drive(
                mock_google_drive,
                folder_id="test_folder",
                file_path="/tmp/test.pdf",
                file_name="test.pdf",
            )

            # Verify permissions().create() was NOT called with type="anyone"
            # Check all calls to permissions().create()
            for c in mock_google_drive.permissions.return_value.create.call_args_list:
                if c.kwargs.get("body") or (c.args and len(c.args) > 0):
                    body = c.kwargs.get("body", {})
                    assert body.get("type") != "anyone", (
                        "Security vulnerability: upload_to_drive should NOT create "
                        "'anyone' permission on uploaded files"
                    )

    def test_upload_returns_web_view_link(self, mock_google_drive):
        """Upload should return the webViewLink from the created file."""
        with patch("services.google_drive_utils.MediaFileUpload"):
            from services.google_drive_utils import upload_to_drive

            result = upload_to_drive(
                mock_google_drive,
                folder_id="test_folder",
                file_path="/tmp/test.pdf",
                file_name="test.pdf",
            )

            assert "drive.google.com" in result

    def test_upload_calls_files_create(self, mock_google_drive):
        """Upload should call files().create() with correct metadata."""
        with patch("services.google_drive_utils.MediaFileUpload"):
            from services.google_drive_utils import upload_to_drive

            upload_to_drive(
                mock_google_drive,
                folder_id="test_folder",
                file_path="/tmp/test.pdf",
                file_name="test.pdf",
            )

            mock_google_drive.files.return_value.create.assert_called_once()
            create_call = mock_google_drive.files.return_value.create.call_args
            body = create_call.kwargs.get("body", {})
            assert body["name"] == "test.pdf"
            assert body["parents"] == ["test_folder"]


class TestFindOrCreateFolder:
    """Tests for the find_or_create_folder function."""

    def test_returns_existing_folder_id(self, mock_google_drive):
        """Should return existing folder ID if found."""
        mock_google_drive.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "existing_folder_id", "name": "TestFolder"}]
        }

        from services.google_drive_utils import find_or_create_folder

        result = find_or_create_folder(
            mock_google_drive,
            "TestFolder",
            entity_type="cliente",
            base_folder_id="base_id",
        )

        assert result == "existing_folder_id"

    def test_creates_folder_if_not_found(self, mock_google_drive):
        """Should create a new folder when none exists."""
        mock_google_drive.files.return_value.list.return_value.execute.return_value = {
            "files": []
        }
        mock_google_drive.files.return_value.create.return_value.execute.return_value = {
            "id": "new_folder_id"
        }

        from services.google_drive_utils import find_or_create_folder

        result = find_or_create_folder(
            mock_google_drive,
            "NewFolder",
            entity_type="proveedor",
            base_folder_id="base_id",
        )

        assert result == "new_folder_id"
        mock_google_drive.files.return_value.create.assert_called_once()
