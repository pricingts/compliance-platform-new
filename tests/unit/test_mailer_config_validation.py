"""Tests for services.mailer.validate_mailer_config (startup health check)."""
from __future__ import annotations

import pytest


@pytest.fixture
def _clean_env(monkeypatch):
    for var in (
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)


class TestValidateMailerConfig:
    def test_disabled_is_ok_noop(self, mock_streamlit, _clean_env):
        from services.mailer import validate_mailer_config

        mock_streamlit["secrets"]["mailer"] = {"enabled": False}
        result = validate_mailer_config()
        assert result["enabled"] is False
        assert result["ok"] is True
        assert result["problems"] == []

    def test_gmail_enabled_with_credentials_ok(self, mock_streamlit, _clean_env):
        from services.mailer import validate_mailer_config

        # mock_streamlit already provides google_sheets_credentials.
        mock_streamlit["secrets"]["mailer"] = {"enabled": True, "transport": "gmail"}
        result = validate_mailer_config()
        assert result["enabled"] is True
        assert result["transport"] == "gmail"
        assert result["ok"] is True

    def test_gmail_enabled_without_credentials_flags_problem(
        self, mock_streamlit, _clean_env
    ):
        from services.mailer import validate_mailer_config

        mock_streamlit["secrets"]["mailer"] = {"enabled": True, "transport": "gmail"}
        mock_streamlit["secrets"].pop("google_sheets_credentials", None)
        result = validate_mailer_config()
        assert result["ok"] is False
        assert any("gmail" in p.lower() for p in result["problems"])

    def test_smtp_enabled_without_config_flags_problems(
        self, mock_streamlit, _clean_env
    ):
        from services.mailer import validate_mailer_config

        mock_streamlit["secrets"]["mailer"] = {"enabled": True, "transport": "smtp"}
        mock_streamlit["secrets"].pop("smtp", None)
        result = validate_mailer_config()
        assert result["ok"] is False
        assert any("smtp" in p.lower() for p in result["problems"])

    def test_smtp_enabled_with_config_ok(self, mock_streamlit, _clean_env):
        from services.mailer import validate_mailer_config

        mock_streamlit["secrets"]["mailer"] = {"enabled": True, "transport": "smtp"}
        mock_streamlit["secrets"]["smtp"] = {
            "host": "smtp.example.com",
            "username": "mailer@tradingsolutions.com",
            "password": "secret",
        }
        result = validate_mailer_config()
        assert result["ok"] is True
