"""Tests for utils/ui_helpers.py — theme UI helpers."""


class TestStatusBadge:
    def test_aprobado_badge_has_green_color(self):
        from utils.ui_helpers import status_badge
        html = status_badge("aprobado")
        assert "status-badge" in html
        assert "#10b981" in html
        assert "aprobado" in html

    def test_pendiente_badge_has_gray_color(self):
        from utils.ui_helpers import status_badge
        html = status_badge("pendiente")
        assert "#94a3b8" in html

    def test_unknown_status_uses_default(self):
        from utils.ui_helpers import status_badge
        html = status_badge("unknown status")
        assert "status-badge" in html
        assert "#94a3b8" in html

    def test_case_insensitive(self):
        from utils.ui_helpers import status_badge
        html = status_badge("APROBADO")
        assert "#10b981" in html

    def test_en_revision_badge(self):
        from utils.ui_helpers import status_badge
        html = status_badge("en revision")
        assert "#f59e0b" in html

    def test_rechazado_badge(self):
        from utils.ui_helpers import status_badge
        html = status_badge("rechazado")
        assert "#ef4444" in html


class TestRenderSectionHeader:
    def test_renders_html_with_title(self):
        from unittest.mock import patch
        from utils.ui_helpers import render_section_header

        with patch("utils.ui_helpers.st") as mock_st:
            render_section_header("Test Section")
            mock_st.markdown.assert_called_once()
            call_html = mock_st.markdown.call_args[0][0]
            assert "form-section-header" in call_html
            assert "Test Section" in call_html
