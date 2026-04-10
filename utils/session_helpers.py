"""Session lifecycle utilities for safe database access."""
from contextlib import contextmanager
from database.db import SessionLocal


@contextmanager
def get_session():
    """Provide a transactional session that auto-closes.

    Usage:
        with get_session() as session:
            data = session.execute(...)
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
