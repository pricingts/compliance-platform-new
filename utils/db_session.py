"""Transactional SQLAlchemy session context manager.

Usage:
    from utils.db_session import transactional_session

    with transactional_session() as session:
        session.add(obj)
        # commit happens automatically on clean exit; rollback on exception.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

from sqlalchemy.orm import Session

from database.db import SessionLocal
from services.logging_config import get_logger

logger = get_logger(__name__)


@contextlib.contextmanager
def transactional_session() -> Iterator[Session]:
    """Yield a SQLAlchemy session that commits on success and rolls back on
    exception, always closing the session in the ``finally`` block.

    Raises:
        Re-raises any exception raised inside the ``with`` block after rolling
        back the transaction.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:  # intentional-broad: any failure inside the `with` block
        # must roll back the transaction and propagate. Narrowing to
        # SQLAlchemyError would leak half-committed state on KeyboardInterrupt
        # or app-level exceptions raised by the caller.
        session.rollback()
        raise
    finally:
        session.close()
