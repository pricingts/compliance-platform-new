"""Tests for the progress view module (forms/view_progress.py).

Bug 1: st.set_page_config() must NOT be called in view_progress.py because
       app.py already calls it. Streamlit only allows one call per session.

Bug 2: The comments section (get_comments_by_request) must be INSIDE the
       ``for r in filtered_requests`` loop, not outside it.
"""

import ast
import textwrap

import pytest


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
