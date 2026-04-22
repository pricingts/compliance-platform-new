"""Tests for utils.db_session.transactional_session context manager."""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def test_session_factory(monkeypatch):
    """Build a SessionLocal bound to an in-memory SQLite and monkeypatch it
    into utils.db_session, then return the factory for test inspection."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT)"))
        conn.commit()

    TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    import utils.db_session as db_session_mod
    monkeypatch.setattr(db_session_mod, "SessionLocal", TestSessionLocal)

    yield TestSessionLocal
    engine.dispose()


def test_transactional_session_commits_on_success(test_session_factory):
    from utils.db_session import transactional_session

    with transactional_session() as session:
        session.execute(text("INSERT INTO kv (k, v) VALUES ('a', '1')"))

    # Verify persistence via a fresh session
    fresh = test_session_factory()
    try:
        rows = fresh.execute(text("SELECT v FROM kv WHERE k='a'")).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "1"
    finally:
        fresh.close()


def test_transactional_session_rolls_back_on_exception(test_session_factory):
    from utils.db_session import transactional_session

    with pytest.raises(RuntimeError):
        with transactional_session() as session:
            session.execute(text("INSERT INTO kv (k, v) VALUES ('b', '2')"))
            raise RuntimeError("boom")

    # Verify no row persisted
    fresh = test_session_factory()
    try:
        rows = fresh.execute(text("SELECT v FROM kv WHERE k='b'")).fetchall()
        assert rows == []
    finally:
        fresh.close()


def test_transactional_session_closes_in_finally(monkeypatch):
    """close() must be called on both success and failure paths."""
    from utils import db_session as db_session_mod

    # Success path
    mock_session_success = MagicMock()
    factory_success = MagicMock(return_value=mock_session_success)
    monkeypatch.setattr(db_session_mod, "SessionLocal", factory_success)

    with db_session_mod.transactional_session():
        pass

    mock_session_success.commit.assert_called_once()
    mock_session_success.close.assert_called_once()
    mock_session_success.rollback.assert_not_called()

    # Failure path
    mock_session_fail = MagicMock()
    factory_fail = MagicMock(return_value=mock_session_fail)
    monkeypatch.setattr(db_session_mod, "SessionLocal", factory_fail)

    with pytest.raises(ValueError):
        with db_session_mod.transactional_session():
            raise ValueError("nope")

    mock_session_fail.rollback.assert_called_once()
    mock_session_fail.close.assert_called_once()
    mock_session_fail.commit.assert_not_called()


def test_transactional_session_re_raises_exception(monkeypatch):
    from utils import db_session as db_session_mod

    monkeypatch.setattr(db_session_mod, "SessionLocal", MagicMock(return_value=MagicMock()))

    class CustomErr(Exception):
        pass

    with pytest.raises(CustomErr, match="original"):
        with db_session_mod.transactional_session():
            raise CustomErr("original")
