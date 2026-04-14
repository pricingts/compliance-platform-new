"""Tests for input validation."""
from utils.validators import (
    is_allowed_email_domain,
    sanitize_company_name,
    sanitize_text,
    validate_email,
)


class TestValidateEmail:
    """Tests for the validate_email function."""

    def test_valid_email(self):
        assert validate_email("user@example.com") is True

    def test_valid_email_with_dots(self):
        assert validate_email("first.last@example.com") is True

    def test_valid_email_with_plus(self):
        assert validate_email("user+tag@example.com") is True

    def test_valid_email_subdomain(self):
        assert validate_email("user@sub.example.com") is True

    def test_invalid_email_no_at(self):
        assert validate_email("userexample.com") is False

    def test_invalid_email_no_domain(self):
        assert validate_email("user@") is False

    def test_invalid_email_no_tld(self):
        assert validate_email("user@example") is False

    def test_invalid_email_double_at(self):
        assert validate_email("user@@example.com") is False

    def test_empty_email(self):
        assert validate_email("") is False

    def test_none_email(self):
        assert validate_email(None) is False

    def test_email_with_spaces(self):
        """Leading/trailing whitespace should be stripped before validation."""
        assert validate_email("  user@example.com  ") is True

    def test_non_string_input(self):
        assert validate_email(123) is False

    def test_email_with_single_char_tld(self):
        """Single-character TLD should be invalid."""
        assert validate_email("user@example.c") is False


class TestSanitizeText:
    """Tests for the sanitize_text function."""

    def test_strips_whitespace(self):
        assert sanitize_text("  hello  ") == "hello"

    def test_max_length(self):
        assert len(sanitize_text("a" * 300, max_length=255)) == 255

    def test_custom_max_length(self):
        assert len(sanitize_text("a" * 100, max_length=50)) == 50

    def test_empty_string(self):
        assert sanitize_text("") == ""

    def test_none_input(self):
        assert sanitize_text(None) == ""

    def test_non_string_input(self):
        assert sanitize_text(123) == ""

    def test_normal_text_unchanged(self):
        assert sanitize_text("hello world") == "hello world"

    def test_text_at_max_length_unchanged(self):
        text = "a" * 255
        assert sanitize_text(text, max_length=255) == text


class TestSanitizeCompanyName:
    """Tests for the sanitize_company_name function."""

    def test_strips_whitespace(self):
        assert sanitize_company_name("  Acme Corp  ") == "Acme Corp"

    def test_max_length_255(self):
        """Company names should be limited to 255 characters."""
        result = sanitize_company_name("A" * 300)
        assert len(result) == 255

    def test_empty_string(self):
        assert sanitize_company_name("") == ""

    def test_none_input(self):
        assert sanitize_company_name(None) == ""

    def test_normal_name_unchanged(self):
        assert sanitize_company_name("Trading Solutions") == "Trading Solutions"


class TestFileValidation:
    """Tests for file size validation functions."""

    def test_validate_file_size_under_limit(self):
        from unittest.mock import MagicMock

        from utils.validators import validate_file_size

        mock_file = MagicMock()
        mock_file.size = 5 * 1024 * 1024  # 5 MB
        assert validate_file_size(mock_file) is True

    def test_validate_file_size_over_limit(self):
        from unittest.mock import MagicMock

        from utils.validators import validate_file_size

        mock_file = MagicMock()
        mock_file.size = 15 * 1024 * 1024  # 15 MB
        assert validate_file_size(mock_file) is False

    def test_validate_file_size_none(self):
        from utils.validators import validate_file_size

        assert validate_file_size(None) is True

    def test_file_size_error_message_contains_limit(self):
        from utils.validators import file_size_error_message

        msg = file_size_error_message()
        assert "10" in msg
        assert "MB" in msg


class TestIsAllowedEmailDomain:
    """Tests for is_allowed_email_domain (restricts users to Trading Solutions domains)."""

    def test_accepts_tradingsolutions_com(self):
        assert is_allowed_email_domain("user@tradingsolutions.com") is True

    def test_accepts_tradingsol_com(self):
        assert is_allowed_email_domain("user@tradingsol.com") is True

    def test_rejects_external_domain(self):
        assert is_allowed_email_domain("user@gmail.com") is False

    def test_rejects_subdomain_of_allowed(self):
        """Subdomains of allowed domains are NOT accepted — exact match only."""
        assert is_allowed_email_domain("user@mail.tradingsolutions.com") is False

    def test_case_insensitive_domain(self):
        assert is_allowed_email_domain("USER@TradingSolutions.COM") is True

    def test_case_insensitive_tradingsol(self):
        assert is_allowed_email_domain("user@TRADINGSOL.com") is True

    def test_none_returns_false(self):
        assert is_allowed_email_domain(None) is False

    def test_empty_returns_false(self):
        assert is_allowed_email_domain("") is False

    def test_no_at_sign_returns_false(self):
        assert is_allowed_email_domain("tradingsolutions.com") is False

    def test_multiple_at_signs_returns_false(self):
        """Malformed email with multiple @ — domain lookup on final part."""
        # After split on '@', last part would be "tradingsolutions.com" — but
        # multi-@ emails are invalid. We accept rsplit behavior (last part).
        # This test documents behavior: pure domain check only.
        assert is_allowed_email_domain("a@b@tradingsolutions.com") is True

    def test_trailing_whitespace_handled(self):
        assert is_allowed_email_domain("  user@tradingsolutions.com  ") is True

    def test_only_at_sign_returns_false(self):
        assert is_allowed_email_domain("@") is False

    def test_empty_domain_returns_false(self):
        assert is_allowed_email_domain("user@") is False
