"""Tests for utils.error_handlers.sanitize_for_user."""


def test_sanitize_validation_error_returns_own_message():
    from utils.error_handlers import sanitize_for_user
    from utils.exceptions import ValidationError

    msg = sanitize_for_user(ValidationError("El email es obligatorio."))
    assert msg == "El email es obligatorio."


def test_sanitize_database_error_returns_user_friendly():
    from utils.error_handlers import sanitize_for_user
    from utils.exceptions import DatabaseError

    msg = sanitize_for_user(DatabaseError("connection refused at pg-host:5432"))
    assert "base de datos" in msg.lower()
    assert "pg-host" not in msg  # no technical leak


def test_sanitize_drive_error_returns_user_friendly():
    from utils.error_handlers import sanitize_for_user
    from utils.exceptions import DriveUploadError

    msg = sanitize_for_user(DriveUploadError("403 Forbidden", file_name="x.pdf"))
    assert "drive" in msg.lower()


def test_sanitize_authentication_error_returns_user_friendly():
    from utils.error_handlers import sanitize_for_user
    from utils.exceptions import AuthenticationError

    msg = sanitize_for_user(AuthenticationError("JWT expired"))
    assert "autenticación" in msg.lower() or "sesión" in msg.lower()


def test_sanitize_mailer_error_returns_user_friendly():
    from utils.error_handlers import sanitize_for_user
    from utils.exceptions import MailerError

    msg = sanitize_for_user(MailerError("SMTP connection timeout"))
    assert "correo" in msg.lower()
    assert "SMTP" not in msg


def test_sanitize_unknown_exception_returns_default():
    from utils.error_handlers import sanitize_for_user

    msg = sanitize_for_user(KeyError("some_key"))
    assert msg == "Ocurrió un error inesperado."

    custom_default = "Algo falló."
    assert sanitize_for_user(ValueError("x"), default=custom_default) == custom_default


def test_sanitize_never_includes_exception_type_name():
    """Sanitized messages must not leak technical exception class names."""
    from utils.error_handlers import sanitize_for_user
    from utils.exceptions import (
        AuthenticationError,
        DatabaseError,
        DriveUploadError,
        MailerError,
    )

    exc_cases = [
        DatabaseError("raw"),
        DriveUploadError("raw"),
        AuthenticationError("raw"),
        MailerError("raw"),
        RuntimeError("raw"),
    ]
    forbidden_fragments = [
        "DatabaseError",
        "DriveUploadError",
        "AuthenticationError",
        "MailerError",
        "RuntimeError",
        "SQLAlchemyError",
        "HttpError",
        "Traceback",
    ]
    for exc in exc_cases:
        result = sanitize_for_user(exc)
        for fragment in forbidden_fragments:
            assert fragment not in result, f"'{fragment}' leaked in sanitize for {type(exc).__name__}"


def test_sanitize_base_compliance_error_falls_back_to_default():
    from utils.error_handlers import sanitize_for_user
    from utils.exceptions import ComplianceError

    msg = sanitize_for_user(ComplianceError("internal x"))
    assert msg == "Ocurrió un error inesperado."
