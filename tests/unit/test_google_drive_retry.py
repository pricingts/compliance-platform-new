"""Tests for retry and timeout hardening in services/google_drive_utils.

Phase 5 adds:
- @with_retry on Drive I/O functions (upload_to_drive, find_or_create_folder,
  find_or_create_subfolder). Retries on HttpError / OSError / ConnectionError /
  TimeoutError up to 3 attempts with exponential backoff.
- Authentication failures (google.auth.exceptions.RefreshError) are NOT
  retried — they propagate immediately.
- On terminal Drive failures, callers receive a DriveUploadError so the UI
  layer can use sanitize_for_user uniformly.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Disable real sleep in utils.retry so tests are fast."""
    import utils.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)


def _make_http_error():
    """Build a minimal googleapiclient.errors.HttpError for tests."""
    from googleapiclient.errors import HttpError
    resp = MagicMock()
    resp.status = 503
    resp.reason = "Service Unavailable"
    return HttpError(resp, b"fail")


class TestUploadRetry:
    def test_upload_retries_on_http_error_then_succeeds(self, mock_streamlit, tmp_path, monkeypatch):
        """HttpError on the first 2 attempts should be retried; success on the 3rd returns webViewLink."""
        from services import google_drive_utils as gdu

        # Stub MediaFileUpload so no real file I/O is needed
        monkeypatch.setattr(gdu, "MediaFileUpload", lambda *a, **kw: MagicMock())

        # Track call count; fail first 2 then succeed
        attempts = {"n": 0}

        def _execute():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise _make_http_error()
            return {
                "id": "final_file_id",
                "webViewLink": "https://drive.google.com/file/d/final_file_id/view",
            }

        service = MagicMock()
        service.files.return_value.create.return_value.execute.side_effect = _execute

        f = tmp_path / "ok.pdf"
        f.write_bytes(b"%PDF-1.4\n")

        link = gdu.upload_to_drive(service, "folder_id", str(f), "ok.pdf")

        assert "drive.google.com" in link
        assert attempts["n"] == 3

    def test_upload_gives_up_after_max_attempts(self, mock_streamlit, tmp_path, monkeypatch):
        """If HttpError keeps firing, after max_attempts the wrapper raises DriveUploadError."""
        from services import google_drive_utils as gdu
        from utils.exceptions import DriveUploadError

        monkeypatch.setattr(gdu, "MediaFileUpload", lambda *a, **kw: MagicMock())

        attempts = {"n": 0}

        def _always_fail():
            attempts["n"] += 1
            raise _make_http_error()

        service = MagicMock()
        service.files.return_value.create.return_value.execute.side_effect = _always_fail

        f = tmp_path / "fail.pdf"
        f.write_bytes(b"%PDF-1.4\n")

        with pytest.raises(DriveUploadError):
            gdu.upload_to_drive(service, "folder_id", str(f), "fail.pdf")

        # 3 attempts total (max_attempts=3)
        assert attempts["n"] == 3

    def test_upload_does_not_retry_on_refresh_error(self, mock_streamlit, tmp_path, monkeypatch):
        """RefreshError indicates bad credentials — must NOT retry, must propagate."""
        from google.auth.exceptions import RefreshError

        from services import google_drive_utils as gdu

        monkeypatch.setattr(gdu, "MediaFileUpload", lambda *a, **kw: MagicMock())

        attempts = {"n": 0}

        def _auth_fail():
            attempts["n"] += 1
            raise RefreshError("invalid_grant")

        service = MagicMock()
        service.files.return_value.create.return_value.execute.side_effect = _auth_fail

        f = tmp_path / "auth.pdf"
        f.write_bytes(b"%PDF-1.4\n")

        with pytest.raises(RefreshError):
            gdu.upload_to_drive(service, "folder_id", str(f), "auth.pdf")

        # Single attempt, no retries
        assert attempts["n"] == 1
