# utils/validators.py
import re

from config.constants import ALLOWED_EMAIL_DOMAINS, MAX_UPLOAD_FILE_SIZE_BYTES, MAX_UPLOAD_FILE_SIZE_MB

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


def validate_file_size(uploaded_file) -> bool:
    """Check that a Streamlit UploadedFile is within size limits.

    Returns True if file is None or within limit.
    """
    if uploaded_file is None:
        return True
    return uploaded_file.size <= MAX_UPLOAD_FILE_SIZE_BYTES


def file_size_error_message() -> str:
    """Return user-facing error message for oversized files."""
    return f"El archivo excede el tamano maximo permitido ({MAX_UPLOAD_FILE_SIZE_MB} MB)."


def is_allowed_email_domain(email: str) -> bool:
    """Return True if the email's domain is in ALLOWED_EMAIL_DOMAINS.

    - Case-insensitive domain comparison.
    - Returns False for None, empty, or strings without '@'.
    - Exact domain match only (subdomains of allowed domains are NOT accepted).
    """
    if not email or not isinstance(email, str):
        return False
    stripped = email.strip()
    if "@" not in stripped:
        return False
    # rsplit on last '@' — robust against malformed input with multiple '@'.
    domain = stripped.rsplit("@", 1)[1].lower()
    if not domain:
        return False
    return domain in {d.lower() for d in ALLOWED_EMAIL_DOMAINS}
