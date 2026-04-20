"""Tests for database/crud/email_threads.py.

Covers the thread-persistence layer used by the Gmail API mailer so that
reminders and status-change emails thread into the same Gmail conversation
as the original request creation email.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture
def request_id(db_session, seed_profiles):
    """Seed a single request row and return its id."""
    db_session.execute(
        text(
            """
            INSERT INTO requests (profile_id, company_name, user_email)
            VALUES (:pid, 'Acme', 'user@tradingsolutions.com')
            """
        ),
        {"pid": seed_profiles["cliente"]},
    )
    db_session.commit()
    return db_session.execute(text("SELECT id FROM requests LIMIT 1")).scalar()


class TestGetThreadByRequestId:
    def test_get_thread_returns_none_when_missing(self, db_session, request_id):
        from database.crud.email_threads import get_thread_by_request_id

        assert get_thread_by_request_id(db_session, request_id) is None


class TestUpsertThread:
    def test_upsert_inserts_new_thread(self, db_session, request_id):
        from database.crud.email_threads import (
            get_thread_by_request_id,
            upsert_thread,
        )

        upsert_thread(
            db_session,
            request_id=request_id,
            gmail_thread_id="thread-abc-123",
            last_message_id="<msg-1@tradingsolutions.com>",
            references_chain="",
        )
        thread = get_thread_by_request_id(db_session, request_id)
        assert thread is not None
        assert thread["request_id"] == request_id
        assert thread["gmail_thread_id"] == "thread-abc-123"
        assert thread["last_message_id"] == "<msg-1@tradingsolutions.com>"

    def test_upsert_updates_existing_thread(self, db_session, request_id):
        from database.crud.email_threads import (
            get_thread_by_request_id,
            upsert_thread,
        )

        # First insert
        upsert_thread(
            db_session,
            request_id=request_id,
            gmail_thread_id="thread-abc-123",
            last_message_id="<msg-1@tradingsolutions.com>",
        )
        # Update with new last_message_id
        upsert_thread(
            db_session,
            request_id=request_id,
            gmail_thread_id="thread-abc-123",
            last_message_id="<msg-2@tradingsolutions.com>",
        )
        thread = get_thread_by_request_id(db_session, request_id)
        assert thread is not None
        assert thread["last_message_id"] == "<msg-2@tradingsolutions.com>"
        # Ensure no duplicate row was inserted
        count = db_session.execute(
            text("SELECT COUNT(*) FROM email_threads WHERE request_id=:rid"),
            {"rid": request_id},
        ).scalar()
        assert count == 1

    def test_upsert_appends_previous_last_message_id_to_chain(
        self, db_session, request_id
    ):
        from database.crud.email_threads import (
            get_thread_by_request_id,
            upsert_thread,
        )

        # First event: initial send
        upsert_thread(
            db_session,
            request_id=request_id,
            gmail_thread_id="thread-abc-123",
            last_message_id="<msg-1@tradingsolutions.com>",
        )
        # Second event: a reminder — previous last_message_id should be
        # appended to the references chain.
        upsert_thread(
            db_session,
            request_id=request_id,
            gmail_thread_id="thread-abc-123",
            last_message_id="<msg-2@tradingsolutions.com>",
        )
        thread = get_thread_by_request_id(db_session, request_id)
        assert thread is not None
        assert "<msg-1@tradingsolutions.com>" in (thread["references_chain"] or "")

        # Third event: chain continues to grow monotonically.
        upsert_thread(
            db_session,
            request_id=request_id,
            gmail_thread_id="thread-abc-123",
            last_message_id="<msg-3@tradingsolutions.com>",
        )
        thread = get_thread_by_request_id(db_session, request_id)
        chain = thread["references_chain"] or ""
        assert "<msg-1@tradingsolutions.com>" in chain
        assert "<msg-2@tradingsolutions.com>" in chain

    def test_upsert_preserves_gmail_thread_id_when_tid_is_none(
        self, db_session, request_id
    ):
        """COALESCE: passing None for gmail_thread_id should keep the existing value."""
        from database.crud.email_threads import (
            get_thread_by_request_id,
            upsert_thread,
        )

        # First: insert with a thread id
        upsert_thread(
            db_session,
            request_id=request_id,
            gmail_thread_id="thread-abc-123",
            last_message_id="<msg-1@tradingsolutions.com>",
        )
        # Second: update with None thread id (simulates a send that failed to
        # return a threadId) — the stored value must not be overwritten.
        upsert_thread(
            db_session,
            request_id=request_id,
            gmail_thread_id=None,
            last_message_id="<msg-2@tradingsolutions.com>",
        )
        thread = get_thread_by_request_id(db_session, request_id)
        assert thread is not None
        assert thread["gmail_thread_id"] == "thread-abc-123"
        assert thread["last_message_id"] == "<msg-2@tradingsolutions.com>"
