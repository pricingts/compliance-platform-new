"""Tests for the progress view module (forms/view_progress.py).

Bug 1: st.set_page_config() must NOT be called in view_progress.py because
       app.py already calls it. Streamlit only allows one call per session.

Bug 2: The comments section (get_comments_by_request) must be INSIDE the
       ``for r in filtered_requests`` loop, not outside it.
"""

import ast

import pytest
from sqlalchemy import text


class TestProgressView:
    """Static analysis tests that verify structural bugs are fixed."""

    def test_no_duplicate_set_page_config(self):
        """view_progress.py should NOT call st.set_page_config anywhere."""
        with open("forms/view_progress.py") as f:
            source = f.read()

        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Match st.set_page_config(...)
                if isinstance(func, ast.Attribute) and func.attr == "set_page_config":
                    pytest.fail(
                        f"view_progress.py should not call st.set_page_config "
                        f"(found at line {node.lineno}). "
                        f"It is already called in app.py."
                    )

    def test_comments_inside_loop(self):
        """The comments_data block must be inside the 'for r in filtered_requests' loop.

        We verify this by checking that the ``comments_data = get_comments_by_request(...)``
        line has indentation >= the indentation of the loop body (i.e., deeper than the
        ``for`` statement itself).
        """
        with open("forms/view_progress.py") as f:
            lines = f.readlines()

        # Find the 'for r in filtered_requests' line
        for_line_idx = None
        for_indent = None
        for idx, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith("for r in filtered_requests"):
                for_line_idx = idx
                for_indent = len(line) - len(stripped)
                break

        assert for_line_idx is not None, (
            "Could not find 'for r in filtered_requests' in view_progress.py"
        )

        # Find the 'comments_data = get_comments_by_request' line
        comments_line_idx = None
        comments_indent = None
        for idx, line in enumerate(lines):
            stripped = line.lstrip()
            if "comments_data" in stripped and "get_comments_by_request" in stripped:
                comments_line_idx = idx
                comments_indent = len(line) - len(stripped)
                break

        assert comments_line_idx is not None, (
            "Could not find 'comments_data = get_comments_by_request(...)' "
            "in view_progress.py"
        )

        # The comments line must be AFTER the for line
        assert comments_line_idx > for_line_idx, (
            "comments_data line should come after the for loop line"
        )

        # The comments line must be indented MORE than the for line
        # (i.e., it must be inside the loop body)
        assert comments_indent > for_indent, (
            f"comments_data (indent={comments_indent}, line {comments_line_idx + 1}) "
            f"must be indented deeper than the for loop (indent={for_indent}, "
            f"line {for_line_idx + 1}). It appears to be OUTSIDE the loop."
        )


class TestProgressPagination:
    """Integration tests for paginated get_requests_for_progress."""

    def test_get_requests_for_progress_pagination(self, db_session, seed_profiles):
        from database.crud.documents import get_requests_for_progress

        for i in range(5):
            db_session.execute(
                text(
                    "INSERT INTO requests (profile_id, company_name, user_email)"
                    " VALUES (:pid, :name, :email)"
                ),
                {
                    "pid": seed_profiles["cliente"],
                    "name": f"Co {i}",
                    "email": "test@test.com",
                },
            )
        db_session.commit()

        results, total = get_requests_for_progress(db_session, page=0, page_size=2)
        assert total == 5
        assert len(results) == 2

        results, total = get_requests_for_progress(db_session, page=2, page_size=2)
        assert total == 5
        assert len(results) == 1


class TestProgressNotesAndMscDetails:
    """The comercial's notes and MSC shipping detail must be retrievable so the
    compliance review screen (view_progress) can display them."""

    def test_get_requests_for_progress_includes_notes(self, db_session, seed_profiles):
        from database.crud.documents import get_requests_for_progress

        db_session.execute(
            text(
                "INSERT INTO requests (profile_id, company_name, user_email, notes)"
                " VALUES (:pid, :name, :email, :notes)"
            ),
            {
                "pid": seed_profiles["cliente"],
                "name": "Acme",
                "email": "t@t.com",
                "notes": "POL: Cartagena / POD: Shanghai",
            },
        )
        db_session.commit()

        results, _ = get_requests_for_progress(db_session)
        assert results[0]["notes"] == "POL: Cartagena / POD: Shanghai"

    def test_get_shipping_lines_status_includes_msc_details(
        self, db_session, seed_profiles
    ):
        from database.crud.clientes import (
            insert_client_request,
            insert_shipping_line_registration,
        )
        from database.crud.documents import get_shipping_lines_status

        rid = insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme",
            has_shipping_line=True,
        )
        insert_shipping_line_registration(
            db_session,
            rid,
            {
                "MSC": {
                    "POL": "Cartagena",
                    "POD": "Shanghai",
                    "Producto": "Coffee",
                    "Tipo de Contenedor": "40HC",
                    "Shipper en BL": "ACME S.A.",
                }
            },
        )

        rows = get_shipping_lines_status(db_session, rid)
        assert rows[0].line_name == "MSC"
        assert rows[0].pol == "Cartagena"
        assert rows[0].pod == "Shanghai"
        assert rows[0].product == "Coffee"
        assert rows[0].container_type == "40HC"
        assert rows[0].shipper_bl == "ACME S.A."
