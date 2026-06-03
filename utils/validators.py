# utils/validators.py
import re

from config.constants import ALLOWED_EMAIL_DOMAINS, MAX_UPLOAD_FILE_SIZE_BYTES, MAX_UPLOAD_FILE_SIZE_MB

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_RE.match(email.strip()))


def validate_emails(value: str) -> bool:
    """Validate one OR many emails separated by comma/semicolon.

    Lets a comercial register several client contact addresses in one field.
    Returns True only when there is at least one address and every address is
    well-formed. Any CR/LF in the input is rejected outright (header-injection
    guard) — a single email with a trailing newline would otherwise slip past
    EMAIL_RE because ``$`` matches before a trailing ``\\n``.
    """
    if not value or not isinstance(value, str):
        return False
    if "\n" in value or "\r" in value:
        return False
    parts = [p.strip() for p in re.split(r"[,;]", value)]
    parts = [p for p in parts if p]
    if not parts:
        return False
    return all(EMAIL_RE.match(p) for p in parts)


def normalize_emails(value: str) -> str:
    """Canonical storage form for one/many emails.

    Drops CR/LF, splits on comma/semicolon, trims each address, removes
    case-insensitive duplicates (keeping first occurrence and original casing),
    and re-joins with ``", "``. Returns ``""`` for empty/None/non-str input.
    """
    if not value or not isinstance(value, str):
        return ""
    cleaned = value.replace("\r", " ").replace("\n", " ")
    seen: set[str] = set()
    out: list[str] = []
    for part in re.split(r"[,;]", cleaned):
        addr = part.strip()
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(addr)
    return ", ".join(out)


def sanitize_text(text: str, max_length: int = 255) -> str:
    """Sanitize text input: drop CR/LF, strip whitespace, limit length.

    CR/LF are collapsed to spaces so values that later flow into email headers
    (e.g. the notification subject's company_name) cannot inject headers.
    """
    if not text or not isinstance(text, str):
        return ""
    cleaned = text.replace("\r", " ").replace("\n", " ")
    return cleaned.strip()[:max_length]


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
