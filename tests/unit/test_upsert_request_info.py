"""Tests for upsert_request_info CRUD (database/crud/documents.py).

Regression coverage for the 2026-04-20 production bug where saving the
upload form without any documents raised::

    psycopg2.errors.NotNullViolation: null value in column "doc_type_id"
    of relation "registration" violates not-null constraint

``upsert_request_info`` persists request-level metadata (``razon_social`` /
``fecha_creacion``) on the ``registration`` table. When no row exists for
the request yet (e.g. user fills metadata before uploading any file), it
inserts a placeholder row with ``file_name = '-'`` and ``doc_type_id`` left
NULL. This requires the column to stay nullable (see migration 007 and
init_db.sql).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database.crud.documents import upsert_request_info


def _insert_request(session, profile_id):
    """Insert a minimal request row and return its id."""
    session.execute(
        text(
            "INSERT INTO requests (profile_id, company_name) "
            "VALUES (:pid, 'Acme')"
        ),
        {"pid": profile_id},
    )
    session.commit()
    return session.execute(text("SELECT MAX(id) FROM requests")).scalar()


class TestUpsertRequestInfoInsertPath:
    """When no registration row exists for the request yet."""

    def test_insert_placeholder_row_with_metadata(
        self, db_session, seed_profiles
    ):
        """A minimal placeholder row is inserted with the metadata set."""
        request_id = _insert_request(db_session, seed_profiles["cliente"])

        upsert_request_info(
            db_session,
            request_id=request_id,
            uploaded_by="Jissel Solares",
            razon_social="Acme SAS",
            fecha_creacion=date(2026, 4, 20),
        )
        db_session.commit()

        row = db_session.execute(
            text(
                "SELECT razon_social, fecha_creacion, doc_type_id, "
                "file_name, uploaded_by "
                "FROM registration WHERE request_id = :rid"
            ),
            {"rid": request_id},
        ).fetchone()
        assert row is not None
        assert row[0] == "Acme SAS"
        assert row[1] == "2026-04-20"  # SQLite stores DATE as ISO string
        assert row[2] is None  # doc_type_id must be nullable for this path
        assert row[3] == "-"   # placeholder file_name
        assert row[4] == "Jissel Solares"

    def test_insert_does_not_crash_with_empty_razon_social(
        self, db_session, seed_profiles
    ):
        """Reproduces the exact prod payload (empty razon_social)."""
        request_id = _insert_request(db_session, seed_profiles["cliente"])

        # Matches the failing prod params byte-for-byte
        upsert_request_info(
            db_session,
            request_id=request_id,
            uploaded_by="Jissel Solares",
            razon_social="",
            fecha_creacion=date(2026, 4, 20),
        )
        db_session.commit()

        count = db_session.execute(
            text("SELECT COUNT(*) FROM registration WHERE request_id = :rid"),
            {"rid": request_id},
        ).scalar()
        assert count == 1


class TestUpsertRequestInfoUpdatePath:
    """When a registration row already exists, metadata is updated in place."""

    def test_update_existing_rows_metadata(self, db_session, seed_profiles):
        request_id = _insert_request(db_session, seed_profiles["cliente"])

        # Simulate a prior document upload
        db_session.execute(
            text(
                "INSERT INTO registration "
                "(request_id, file_name, uploaded_by, razon_social) "
                "VALUES (:rid, 'contract.pdf', 'Juan', 'Old Name')"
            ),
            {"rid": request_id},
        )
        db_session.commit()

        upsert_request_info(
            db_session,
            request_id=request_id,
            uploaded_by="Juan",
            razon_social="Updated Name",
            fecha_creacion=date(2026, 4, 20),
        )
        db_session.commit()

        rows = db_session.execute(
            text(
                "SELECT razon_social, fecha_creacion, file_name "
                "FROM registration WHERE request_id = :rid"
            ),
            {"rid": request_id},
        ).fetchall()
        assert len(rows) == 1, "UPDATE path must not create a second row"
        assert rows[0][0] == "Updated Name"
        assert rows[0][1] == "2026-04-20"
        assert rows[0][2] == "contract.pdf"  # existing row, not a placeholder


class TestProductionSchemaDivergenceReproduction:
    """Reproduces the production schema bug exactly.

    If ``registration.doc_type_id`` is NOT NULL, ``upsert_request_info``
    must raise ``IntegrityError`` on the INSERT path. This test documents
    *why* migration 007 is required: without it, the prod schema would
    still crash on this call.
    """

    def test_insert_path_crashes_when_doc_type_id_is_not_null(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE requests ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "profile_id INTEGER)"
            ))
            # Reproduce the broken prod constraint exactly
            conn.execute(text(
                "CREATE TABLE registration ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "request_id INTEGER NOT NULL, "
                "doc_type_id INTEGER NOT NULL, "  # <-- the production bug
                "file_name VARCHAR(255), "
                "uploaded_by VARCHAR(150), "
                "razon_social VARCHAR(255), "
                "fecha_creacion DATE)"
            ))
            conn.execute(text(
                "INSERT INTO requests (id, profile_id) VALUES (79, 1)"
            ))

        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            with pytest.raises(IntegrityError):
                upsert_request_info(
                    session,
                    request_id=79,
                    uploaded_by="Jissel Solares",
                    razon_social="",
                    fecha_creacion=date(2026, 4, 20),
                )
                session.commit()
        finally:
            session.rollback()
            session.close()
            engine.dispose()
