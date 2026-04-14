"""Tests for Case ID (C0001...) generation and integration into insert_client_request.

Phase 5 of the compliance platform enhancements (F5).
"""
from __future__ import annotations

from sqlalchemy import text


class TestFormatCaseId:
    def test_pads_to_4_digits(self):
        from database.crud.clientes import format_case_id
        assert format_case_id(1) == "C0001"
        assert format_case_id(42) == "C0042"
        assert format_case_id(100) == "C0100"
        assert format_case_id(9999) == "C9999"

    def test_overflow_4_digits_gracefully(self):
        from database.crud.clientes import format_case_id
        assert format_case_id(10000) == "C10000"
        assert format_case_id(99999) == "C99999"


class TestInsertClientRequestGeneratesCaseId:
    """insert_client_request must populate case_id on the row it just created."""

    def test_first_insert_gets_c0001(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="user@tradingsolutions.com",
        )
        case_id = db_session.execute(
            text("SELECT case_id FROM requests WHERE id=:id"), {"id": rid}
        ).scalar()
        assert case_id == "C0001"

    def test_sequential_inserts_get_sequential_case_ids(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request
        ids = []
        for i in range(3):
            rid = insert_client_request(
                session=db_session,
                profile_id=seed_profiles["cliente"],
                company_name=f"Acme {i}",
                user_email="user@tradingsolutions.com",
            )
            ids.append(rid)
        rows = db_session.execute(
            text("SELECT id, case_id FROM requests WHERE id IN (:a,:b,:c) ORDER BY id"),
            {"a": ids[0], "b": ids[1], "c": ids[2]},
        ).fetchall()
        case_ids = [r[1] for r in rows]
        # All different and match their ids
        assert len(set(case_ids)) == 3
        for i, row in enumerate(rows):
            assert row[1] == f"C{row[0]:04d}"

    def test_returned_request_id_is_integer(self, db_session, seed_profiles):
        """Backward compat: insert_client_request still returns an int id."""
        from database.crud.clientes import insert_client_request
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="user@tradingsolutions.com",
        )
        assert isinstance(rid, int)
        assert rid > 0


class TestGetCaseId:
    def test_returns_case_id_for_existing_request(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request, get_case_id
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="u@tradingsolutions.com",
        )
        assert get_case_id(db_session, rid) == "C0001"

    def test_returns_none_for_missing_request(self, db_session):
        from database.crud.clientes import get_case_id
        assert get_case_id(db_session, 99999) is None


class TestGetRequestByCaseId:
    def test_finds_request_by_case_id(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request, get_request_by_case_id
        rid = insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="u@tradingsolutions.com",
        )
        row = get_request_by_case_id(db_session, "C0001")
        assert row is not None
        assert row["id"] == rid
        assert row["case_id"] == "C0001"
        assert row["company_name"] == "Acme"

    def test_returns_none_for_unknown_case_id(self, db_session):
        from database.crud.clientes import get_request_by_case_id
        assert get_request_by_case_id(db_session, "C9999") is None

    def test_case_insensitive(self, db_session, seed_profiles):
        from database.crud.clientes import insert_client_request, get_request_by_case_id
        insert_client_request(
            session=db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            user_email="u@tradingsolutions.com",
        )
        # Both should work
        assert get_request_by_case_id(db_session, "C0001") is not None
        assert get_request_by_case_id(db_session, "c0001") is not None
