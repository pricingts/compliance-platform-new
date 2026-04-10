"""Tests for authentication service."""
import pytest

class TestAuthentication:
    def test_session_timeout_constant_exists(self):
        """Session timeout should be configurable."""
        from config.settings import get_session_timeout_minutes
        timeout = get_session_timeout_minutes()
        assert isinstance(timeout, int)
        assert timeout > 0

    def test_default_timeout_is_reasonable(self):
        """Default session timeout should be 480 minutes (8 hours)."""
        from config.settings import get_session_timeout_minutes
        timeout = get_session_timeout_minutes()
        assert timeout == 480
