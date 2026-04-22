"""Tests for utils.retry.with_retry decorator."""
import pytest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Globally disable time.sleep within utils.retry so tests run instantly."""
    import utils.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)


def test_with_retry_returns_value_on_first_success():
    from utils.retry import with_retry

    calls = {"n": 0}

    @with_retry(max_attempts=3)
    def ok():
        calls["n"] += 1
        return "ok"

    assert ok() == "ok"
    assert calls["n"] == 1


def test_with_retry_succeeds_on_third_attempt():
    from utils.retry import with_retry

    calls = {"n": 0}

    @with_retry(max_attempts=3, exceptions=(ValueError,))
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_with_retry_gives_up_after_max_attempts():
    from utils.retry import with_retry

    calls = {"n": 0}

    @with_retry(max_attempts=3, exceptions=(ValueError,))
    def always_fails():
        calls["n"] += 1
        raise ValueError(f"fail-{calls['n']}")

    with pytest.raises(ValueError, match="fail-3"):
        always_fails()

    assert calls["n"] == 3


def test_with_retry_only_retries_allowed_exceptions():
    from utils.retry import with_retry

    calls = {"n": 0}

    @with_retry(max_attempts=3, exceptions=(ValueError,))
    def raises_keyerror():
        calls["n"] += 1
        raise KeyError("not allowed")

    with pytest.raises(KeyError):
        raises_keyerror()

    # KeyError is not in the retry list, so no retries — a single attempt.
    assert calls["n"] == 1


def test_with_retry_preserves_function_metadata():
    from utils.retry import with_retry

    @with_retry(max_attempts=2)
    def documented():
        """This is a docstring."""
        return 42

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "This is a docstring."
