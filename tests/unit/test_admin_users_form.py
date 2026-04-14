"""Tests for forms/admin_users_form.py — pure logic helpers.

Focus is on the testable-without-Streamlit helpers:
- _validate_new_user_data
- _can_deactivate

UI rendering (render_admin_users_panel) is exercised via integration smoke
tests elsewhere, not unit-tested here.
"""
from __future__ import annotations

from config.constants import ALLOWED_EMAIL_DOMAINS


class TestValidateNewUserData:
    """Tests for _validate_new_user_data."""

    def test_valid_comercial(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="new@tradingsolutions.com",
            nombre_display="New Comercial",
            rol="comercial",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is True
        assert err == ""

    def test_valid_inside_sales(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="is@tradingsol.com",
            nombre_display="Inside Sales",
            rol="inside_sales",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is True
        assert err == ""

    def test_valid_compliance(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="c@tradingsolutions.com",
            nombre_display="Compliance",
            rol="compliance",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is True

    def test_valid_otro(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="o@tradingsolutions.com",
            nombre_display="Otro",
            rol="otro",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is True

    def test_invalid_rol(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="new@tradingsolutions.com",
            nombre_display="New",
            rol="admin",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is False
        assert "rol" in err.lower()

    def test_blocked_external_domain(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="attacker@gmail.com",
            nombre_display="Attacker",
            rol="comercial",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is False
        assert "dominio" in err.lower() or "domain" in err.lower()

    def test_empty_email(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="",
            nombre_display="Some Name",
            rol="comercial",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is False
        assert "email" in err.lower() or "correo" in err.lower()

    def test_none_email(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email=None,
            nombre_display="Some Name",
            rol="comercial",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is False

    def test_empty_nombre_display(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="new@tradingsolutions.com",
            nombre_display="",
            rol="comercial",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is False
        assert "nombre" in err.lower()

    def test_whitespace_only_nombre_display(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="new@tradingsolutions.com",
            nombre_display="   ",
            rol="comercial",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is False

    def test_empty_rol(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="new@tradingsolutions.com",
            nombre_display="New",
            rol="",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is False

    def test_malformed_email_no_at(self):
        from forms.admin_users_form import _validate_new_user_data

        is_valid, err = _validate_new_user_data(
            email="userplusdomain.com",
            nombre_display="New",
            rol="comercial",
            allowed_domains=ALLOWED_EMAIL_DOMAINS,
        )
        assert is_valid is False


class TestCanDeactivate:
    """Tests for _can_deactivate (super-admin protection)."""

    def test_blocks_super_admin_exact(self):
        from forms.admin_users_form import _can_deactivate

        assert _can_deactivate(
            "jsanchez@tradingsolutions.com",
            super_admin_email="jsanchez@tradingsolutions.com",
        ) is False

    def test_blocks_super_admin_uppercase(self):
        from forms.admin_users_form import _can_deactivate

        assert _can_deactivate(
            "JSANCHEZ@TRADINGSOLUTIONS.COM",
            super_admin_email="jsanchez@tradingsolutions.com",
        ) is False

    def test_blocks_super_admin_mixed_case(self):
        from forms.admin_users_form import _can_deactivate

        assert _can_deactivate(
            "JSanchez@TradingSolutions.com",
            super_admin_email="jsanchez@tradingsolutions.com",
        ) is False

    def test_blocks_super_admin_with_whitespace(self):
        from forms.admin_users_form import _can_deactivate

        assert _can_deactivate(
            "  jsanchez@tradingsolutions.com  ",
            super_admin_email="jsanchez@tradingsolutions.com",
        ) is False

    def test_allows_other_user(self):
        from forms.admin_users_form import _can_deactivate

        assert _can_deactivate(
            "other@tradingsolutions.com",
            super_admin_email="jsanchez@tradingsolutions.com",
        ) is True

    def test_allows_none_email(self):
        """A None/empty email is not the super-admin — returns True (nothing to block)."""
        from forms.admin_users_form import _can_deactivate

        # None shouldn't match — but treat defensively: can't deactivate nothing anyway.
        # Spec: returns False only if email matches super-admin. So None is True.
        assert _can_deactivate(
            None,
            super_admin_email="jsanchez@tradingsolutions.com",
        ) is True
