"""Tests for utils.logging_decorators.log_errors decorator."""
from unittest.mock import MagicMock

import pytest


def test_log_errors_reraises_by_default(monkeypatch):
    import utils.logging_decorators as mod

    mock_logger = MagicMock()
    monkeypatch.setattr(mod, "logger", mock_logger)

    @mod.log_errors()
    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        boom()

    assert mock_logger.exception.called


def test_log_errors_swallows_when_reraise_false(monkeypatch):
    import utils.logging_decorators as mod

    mock_logger = MagicMock()
    monkeypatch.setattr(mod, "logger", mock_logger)

    @mod.log_errors(reraise=False)
    def boom():
        raise ValueError("swallowed")

    result = boom()
    assert result is None
    assert mock_logger.exception.called


def test_log_errors_logs_exception_with_function_context(monkeypatch):
    import utils.logging_decorators as mod

    mock_logger = MagicMock()
    monkeypatch.setattr(mod, "logger", mock_logger)

    @mod.log_errors(reraise=False)
    def my_func(a, b):
        raise RuntimeError("broke")

    my_func(1, 2)

    # The decorator must have called logger.exception with the function name
    # somewhere in its args or extra kwargs.
    assert mock_logger.exception.called
    call_args, call_kwargs = mock_logger.exception.call_args
    extras = call_kwargs.get("extra", {})
    message_blob = " ".join(str(a) for a in call_args)
    assert "my_func" in message_blob or extras.get("function") == "my_func"
    assert extras.get("exception_type") == "RuntimeError"


def test_log_errors_with_user_message_raises_runtime_for_non_compliance(monkeypatch):
    """When reraise=True and user_message set, non-ComplianceError exceptions
    must be re-raised as RuntimeError with the provided message."""
    import utils.logging_decorators as mod

    mock_logger = MagicMock()
    monkeypatch.setattr(mod, "logger", mock_logger)

    @mod.log_errors(reraise=True, user_message="Algo salió mal")
    def boom():
        raise ValueError("low-level detail")

    with pytest.raises(RuntimeError, match="Algo salió mal") as exc_info:
        boom()
    # Original cause must be chained
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_log_errors_with_user_message_preserves_compliance_subclass(monkeypatch):
    """ComplianceError subclasses must be re-raised with their own type."""
    import utils.logging_decorators as mod
    from utils.exceptions import DatabaseError

    mock_logger = MagicMock()
    monkeypatch.setattr(mod, "logger", mock_logger)

    @mod.log_errors(reraise=True, user_message="DB ocupada")
    def boom():
        raise DatabaseError("deadlock")

    with pytest.raises(DatabaseError, match="DB ocupada"):
        boom()
