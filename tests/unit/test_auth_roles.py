"""Tests for role-based access control.

Note: We cannot directly ``from app import identity_role`` in tests because
app.py runs Streamlit UI code at module level (st.set_page_config, st.columns,
etc.).  Instead we replicate the identity_role logic here, which is the exact
same two-line body that app.py uses, and verify it against get_admin_emails().
This ensures the security fix (config-driven admin list) is correctly tested.
"""
import os
from typing import Optional
from unittest.mock import patch
from config.settings import get_admin_emails


def _identity_role(email: Optional[str]) -> str:
    """Mirror of app.identity_role for testing without Streamlit side effects."""
    if not email:
        return "other"
    allowed_emails = get_admin_emails()
    return "compliance" if email.lower() in allowed_emails else "other"


class TestIdentityRole:
    """Tests for the identity_role function logic."""

    def test_compliance_role_for_admin_email(self):
        """Known admin email should get compliance role."""
        admin_emails = get_admin_emails()
        assert len(admin_emails) > 0, "Default admin emails should not be empty"

        sample_email = next(iter(admin_emails))
        assert _identity_role(sample_email) == "compliance"

    def test_other_role_for_unknown_email(self):
        """Unknown email should get 'other' role."""
        assert _identity_role("stranger@gmail.com") == "other"

    def test_none_email_returns_other(self):
        """None email should return 'other'."""
        assert _identity_role(None) == "other"

    def test_empty_string_returns_other(self):
        """Empty string email should return 'other'."""
        assert _identity_role("") == "other"

    def test_case_insensitive(self):
        """Email matching should be case-insensitive."""
        admin_emails = get_admin_emails()
        sample_email = next(iter(admin_emails))
        assert _identity_role(sample_email.upper()) == "compliance"

    def test_configurable_admin_emails(self):
        """Admin emails should come from configuration, not hardcoded."""
        with patch.dict(os.environ, {"ADMIN_EMAILS": "custom@example.com,another@test.org"}):
            emails = get_admin_emails()
            assert "custom@example.com" in emails
            assert "another@test.org" in emails

    def test_configurable_email_grants_compliance(self):
        """An email configured via env var should get compliance role."""
        with patch.dict(os.environ, {"ADMIN_EMAILS": "custom@example.com"}):
            assert _identity_role("custom@example.com") == "compliance"
            assert _identity_role("other@example.com") == "other"


class TestGetAdminEmails:
    """Tests for config.settings.get_admin_emails."""

    def test_returns_set(self):
        """Should return a set of strings."""
        result = get_admin_emails()
        assert isinstance(result, set)
        assert all(isinstance(e, str) for e in result)

    def test_env_var_override(self):
        """ADMIN_EMAILS env var should override defaults."""
        with patch.dict(os.environ, {"ADMIN_EMAILS": "a@b.com,c@d.com"}):
            emails = get_admin_emails()
            assert emails == {"a@b.com", "c@d.com"}

    def test_env_var_strips_whitespace(self):
        """Emails from env var should be stripped of whitespace."""
        with patch.dict(os.environ, {"ADMIN_EMAILS": " a@b.com , c@d.com "}):
            emails = get_admin_emails()
            assert "a@b.com" in emails
            assert "c@d.com" in emails

    def test_env_var_lowercased(self):
        """Emails from env var should be lowercased."""
        with patch.dict(os.environ, {"ADMIN_EMAILS": "Admin@Example.COM"}):
            emails = get_admin_emails()
            assert "admin@example.com" in emails

    def test_fallback_to_usernames_and_domains(self):
        """When ADMIN_EMAILS is not set, should build from usernames and domains."""
        env = {k: v for k, v in os.environ.items() if k != "ADMIN_EMAILS"}
        with patch.dict(os.environ, env, clear=True):
            emails = get_admin_emails()
            assert len(emails) > 0

    def test_custom_usernames_and_domains(self):
        """Custom ADMIN_USERNAMES and ADMIN_DOMAINS should be used when ADMIN_EMAILS is not set."""
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("ADMIN_EMAILS", "ADMIN_USERNAMES", "ADMIN_DOMAINS")}
        env_clean["ADMIN_USERNAMES"] = "alice,bob"
        env_clean["ADMIN_DOMAINS"] = "@test.com"
        with patch.dict(os.environ, env_clean, clear=True):
            emails = get_admin_emails()
            assert "alice@test.com" in emails
            assert "bob@test.com" in emails
