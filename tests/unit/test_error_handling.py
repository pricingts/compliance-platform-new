"""Tests for error handling utilities."""
import logging
from unittest.mock import patch, MagicMock

import pytest

from utils.exceptions import (
    ComplianceError,
    DatabaseError,
    DriveUploadError,
    ValidationError,
    AuthenticationError,
)


class TestExceptionHierarchy:
    """All custom exceptions should inherit from ComplianceError."""

    def test_compliance_error_is_base(self):
        """All custom exceptions inherit from ComplianceError."""
        assert issubclass(DatabaseError, ComplianceError)
        assert issubclass(DriveUploadError, ComplianceError)
        assert issubclass(ValidationError, ComplianceError)
        assert issubclass(AuthenticationError, ComplianceError)

    def test_compliance_error_inherits_from_exception(self):
        """ComplianceError itself inherits from Exception."""
        assert issubclass(ComplianceError, Exception)

    def test_compliance_error_has_message(self):
        err = ComplianceError("test message")
        assert str(err) == "test message"

    def test_database_error_with_original(self):
        original = ValueError("original error")
        err = DatabaseError("DB failed", original_error=original)
        assert err.original_error is original
        assert "DB failed" in str(err)

    def test_database_error_without_original(self):
        err = DatabaseError("DB failed")
        assert err.original_error is None
        assert "DB failed" in str(err)

    def test_validation_error_with_field(self):
        err = ValidationError("Invalid email", field="email")
        assert err.field == "email"
        assert "Invalid email" in str(err)

    def test_validation_error_without_field(self):
        err = ValidationError("Missing value")
        assert err.field is None

    def test_drive_upload_error_with_file_name(self):
        err = DriveUploadError("Upload failed", file_name="test.pdf")
        assert err.file_name == "test.pdf"
        assert "Upload failed" in str(err)

    def test_drive_upload_error_without_file_name(self):
        err = DriveUploadError("Upload failed")
        assert err.file_name is None

    def test_authentication_error(self):
        err = AuthenticationError("Not authorized")
        assert str(err) == "Not authorized"

    def test_catch_all_custom_exceptions(self):
        """A single except ComplianceError block catches all custom exceptions."""
        for exc_class in (DatabaseError, DriveUploadError, ValidationError, AuthenticationError):
            with pytest.raises(ComplianceError):
                raise exc_class("test")


class TestErrorHandlers:
    """Tests for the handle_error utility function."""

    @patch("utils.error_handlers.st")
    def test_handle_error_logs_message(self, mock_st):
        """handle_error should log the error."""
        from utils.error_handlers import handle_error, logger

        with patch.object(logger, "error") as mock_log:
            err = ValueError("something broke")
            handle_error(err)
            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert "ValueError" in call_args[0][0]
            assert "something broke" in call_args[0][0]

    @patch("utils.error_handlers.st")
    def test_handle_error_shows_default_user_message(self, mock_st):
        """handle_error should display a default Spanish error message."""
        from utils.error_handlers import handle_error

        handle_error(RuntimeError("internal crash"))
        mock_st.error.assert_called_once()
        call_args = mock_st.error.call_args[0][0]
        assert "Error" in call_args

    @patch("utils.error_handlers.st")
    def test_handle_error_shows_custom_user_message(self, mock_st):
        """handle_error should display the custom message when provided."""
        from utils.error_handlers import handle_error

        handle_error(RuntimeError("crash"), user_message="Custom message")
        mock_st.error.assert_called_once()
        call_args = mock_st.error.call_args[0][0]
        assert "Custom message" in call_args

    @patch("utils.error_handlers.st")
    def test_handle_error_with_compliance_error(self, mock_st):
        """handle_error should work with custom ComplianceError subclasses."""
        from utils.error_handlers import handle_error, logger

        with patch.object(logger, "error") as mock_log:
            err = DatabaseError("Connection lost", original_error=TimeoutError("timeout"))
            handle_error(err, user_message="Database unavailable")
            mock_log.assert_called_once()
            assert "DatabaseError" in mock_log.call_args[0][0]
        mock_st.error.assert_called_once()
        assert "Database unavailable" in mock_st.error.call_args[0][0]
