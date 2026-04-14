"""Tests for database/crud/request_attachments.py."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture
def request_id(db_session, seed_profiles):
    db_session.execute(text("""
        INSERT INTO requests (profile_id, company_name, user_email)
        VALUES (:pid, 'Acme', 'user@tradingsolutions.com')
    """), {"pid": seed_profiles["cliente"]})
    db_session.commit()
    return db_session.execute(text("SELECT id FROM requests LIMIT 1")).scalar()


class TestInsertRequestAttachment:
    def test_returns_id(self, db_session, request_id):
        from database.crud.request_attachments import insert_request_attachment
        att_id = insert_request_attachment(
            db_session,
            request_id=request_id,
            file_name="doc.pdf",
            drive_link="https://drive.google.com/xxx",
            uploaded_by="user@tradingsolutions.com",
        )
        assert att_id is not None
        assert att_id > 0

    def test_persists_all_fields(self, db_session, request_id):
        from database.crud.request_attachments import insert_request_attachment
        insert_request_attachment(
            db_session,
            request_id=request_id,
            file_name="receipt.docx",
            drive_link="https://drive.google.com/yyy",
            uploaded_by="abc@tradingsol.com",
        )
        row = db_session.execute(text("""
            SELECT request_id, file_name, drive_link, uploaded_by
              FROM request_attachments WHERE request_id=:rid
        """), {"rid": request_id}).fetchone()
        assert row[0] == request_id
        assert row[1] == "receipt.docx"
        assert row[2] == "https://drive.google.com/yyy"
        assert row[3] == "abc@tradingsol.com"


class TestGetRequestAttachments:
    def test_returns_list_for_request(self, db_session, request_id):
        from database.crud.request_attachments import (
            insert_request_attachment, get_request_attachments,
        )
        for n in range(3):
            insert_request_attachment(
                db_session, request_id=request_id,
                file_name=f"f{n}.pdf", drive_link=f"https://drive/{n}",
                uploaded_by="u@tradingsolutions.com",
            )
        attachments = get_request_attachments(db_session, request_id)
        assert len(attachments) == 3
        names = sorted([a["file_name"] for a in attachments])
        assert names == ["f0.pdf", "f1.pdf", "f2.pdf"]

    def test_returns_empty_for_no_attachments(self, db_session, request_id):
        from database.crud.request_attachments import get_request_attachments
        assert get_request_attachments(db_session, request_id) == []


class TestCascadeDelete:
    def test_attachments_removed_when_request_deleted(self, db_session, request_id):
        from database.crud.request_attachments import (
            insert_request_attachment,
        )
        insert_request_attachment(
            db_session, request_id=request_id,
            file_name="x.pdf", drive_link="https://x", uploaded_by="u@tradingsolutions.com",
        )
        db_session.execute(text("DELETE FROM requests WHERE id=:id"), {"id": request_id})
        db_session.commit()
        # Cascade should have deleted the attachment row
        count = db_session.execute(
            text("SELECT COUNT(*) FROM request_attachments WHERE request_id=:rid"),
            {"rid": request_id},
        ).scalar()
        assert count == 0


class TestNotesPersisted:
    def test_insert_with_notes(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="u@tradingsolutions.com",
            notes="Cliente requiere validación adicional de RUT.",
        )
        notes = db_session.execute(
            text("SELECT notes FROM requests WHERE id=:id"), {"id": rid}
        ).scalar()
        assert notes == "Cliente requiere validación adicional de RUT."

    def test_notes_default_none(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="u@tradingsolutions.com",
        )
        notes = db_session.execute(
            text("SELECT notes FROM requests WHERE id=:id"), {"id": rid}
        ).scalar()
        assert notes is None
