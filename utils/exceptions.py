"""Custom exception hierarchy for the compliance platform."""


class ComplianceError(Exception):
    """Base exception for all compliance platform errors."""
    pass


class DatabaseError(ComplianceError):
    """Database operation failures."""

    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error


class DriveUploadError(ComplianceError):
    """Google Drive upload failures."""

    def __init__(self, message: str, file_name: str = None):
        super().__init__(message)
        self.file_name = file_name


class ValidationError(ComplianceError):
    """Input validation failures."""

    def __init__(self, message: str, field: str = None):
        super().__init__(message)
        self.field = field


class AuthenticationError(ComplianceError):
    """Authentication/authorization failures."""
    pass


class MailerError(ComplianceError):
    """Error al enviar notificación por correo."""
    pass


class SheetsError(ComplianceError):
    """Google Sheets operation failures (read/write/worksheet lookup)."""
    pass


class DelegationError(MailerError):
    """Raised when Domain-Wide Delegation is missing or misconfigured.

    Thrown on 401/403 HttpError responses from Gmail API that indicate the
    service account lacks authorization to impersonate the target user for
    the gmail.send scope. The message includes the target user so operators
    can verify the scope is approved for the service account client ID in
    Admin Console.
    """
