# utils/validators.py
import re

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_RE.match(email.strip()))


def sanitize_text(text: str, max_length: int = 255) -> str:
    """Sanitize text input: strip whitespace, limit length."""
    if not text or not isinstance(text, str):
        return ""
    return text.strip()[:max_length]


def sanitize_company_name(name: str) -> str:
    """Sanitize company name input."""
    return sanitize_text(name, max_length=255)
