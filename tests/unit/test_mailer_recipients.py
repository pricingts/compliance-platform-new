"""Tests for services/mailer/recipients.py — recipient resolution logic.

Contract:
- TO = hardcoded compliance team + dynamic compliance users from the DB.
- TO is deduplicated case-insensitively and filtered to allowed domains.
- CC = creator + submitted_by, minus anyone already in TO.
- CC is NOT domain-filtered.
- Both lists are returned sorted.
"""
from __future__ import annotations

from sqlalchemy import text


def _insert_user(session, email, nombre, rol, activo=1):
    session.execute(
        text("""
            INSERT INTO users (email, nombre_display, rol, activo)
            VALUES (:e, :n, :r, :a)
        """),
        {"e": email, "n": nombre, "r": rol, "a": activo},
    )
    session.commit()


class TestResolveRecipients:
    def test_to_list_includes_default_compliance_team(self, db_session):
        from services.mailer.recipients import (
            DEFAULT_COMPLIANCE_RECIPIENTS,
            resolve_recipients,
        )

        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
        )
        for addr in DEFAULT_COMPLIANCE_RECIPIENTS:
            assert addr in out["to"], f"default {addr!r} missing from TO"

    def test_to_list_includes_dynamic_compliance_users(self, db_session):
        from services.mailer.recipients import resolve_recipients

        _insert_user(
            db_session, "newcompliance@tradingsolutions.com", "New Compliance", "compliance"
        )

        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
        )
        assert "newcompliance@tradingsolutions.com" in out["to"]

    def test_to_list_dedupes_case_insensitive(self, db_session):
        from services.mailer.recipients import resolve_recipients

        # This email collides with one of the hardcoded defaults — uppercase.
        _insert_user(
            db_session, "COMPLIANCE1@tradingsolutions.com", "Dup", "compliance"
        )

        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
        )
        lowered = [e.lower() for e in out["to"]]
        assert lowered.count("compliance1@tradingsolutions.com") == 1

    def test_cc_excludes_addresses_already_in_to(self, db_session):
        from services.mailer.recipients import resolve_recipients

        # Creator happens to be one of the compliance defaults.
        out = resolve_recipients(
            db_session,
            creator_email="compliance1@tradingsolutions.com",
        )
        assert "compliance1@tradingsolutions.com" not in out["cc"]

    def test_cc_omits_none_values(self, db_session):
        from services.mailer.recipients import resolve_recipients

        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
            submitted_by_email=None,
        )
        assert "pedro@tradingsolutions.com" in out["cc"]
        assert None not in out["cc"]
        # Only the creator should be in CC; len == 1
        assert len(out["cc"]) == 1

    def test_cc_dedupes_creator_and_submitted_by_when_equal(self, db_session):
        from services.mailer.recipients import resolve_recipients

        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
            submitted_by_email="PEDRO@tradingsolutions.com",
        )
        lowered = [e.lower() for e in out["cc"]]
        assert lowered.count("pedro@tradingsolutions.com") == 1

    def test_to_filters_disallowed_domains(self, db_session):
        from services.mailer.recipients import resolve_recipients

        _insert_user(
            db_session, "external@gmail.com", "External User", "compliance"
        )
        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
        )
        assert "external@gmail.com" not in out["to"]

    def test_resolve_recipients_empty_when_no_compliance_at_all_still_has_hardcoded(
        self, db_session
    ):
        from services.mailer.recipients import (
            DEFAULT_COMPLIANCE_RECIPIENTS,
            resolve_recipients,
        )

        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
        )
        # No compliance users in DB, but hardcoded fallbacks must still be there.
        for addr in DEFAULT_COMPLIANCE_RECIPIENTS:
            assert addr in out["to"]
        assert len(out["to"]) >= len(DEFAULT_COMPLIANCE_RECIPIENTS)


class TestExcludeCreatorFromCc:
    """Phase 8.3: when transport=gmail, From=creator_email so we remove the
    creator from CC to avoid the creator appearing twice (as From and as CC)."""

    def test_exclude_creator_from_cc_removes_creator_when_flag_true(
        self, db_session
    ):
        from services.mailer.recipients import resolve_recipients

        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
            exclude_creator_from_cc=True,
        )
        lowered_cc = [e.lower() for e in out["cc"]]
        assert "pedro@tradingsolutions.com" not in lowered_cc

    def test_exclude_creator_from_cc_keeps_submitted_by_when_flag_true(
        self, db_session
    ):
        """When IS creates on behalf of a comercial, the comercial
        (submitted_by_email) must still land in CC even when the creator
        (the IS) is excluded."""
        from services.mailer.recipients import resolve_recipients

        out = resolve_recipients(
            db_session,
            creator_email="is@tradingsolutions.com",
            submitted_by_email="comercial@tradingsolutions.com",
            exclude_creator_from_cc=True,
        )
        lowered_cc = [e.lower() for e in out["cc"]]
        assert "is@tradingsolutions.com" not in lowered_cc
        assert "comercial@tradingsolutions.com" in lowered_cc

    def test_exclude_creator_from_cc_default_false_preserves_existing_behavior(
        self, db_session
    ):
        """Default (flag omitted) must match the pre-Phase-8.3 behavior:
        creator_email lands in CC."""
        from services.mailer.recipients import resolve_recipients

        out = resolve_recipients(
            db_session,
            creator_email="pedro@tradingsolutions.com",
            submitted_by_email="is@tradingsolutions.com",
        )
        lowered_cc = [e.lower() for e in out["cc"]]
        assert "pedro@tradingsolutions.com" in lowered_cc
        assert "is@tradingsolutions.com" in lowered_cc

    def test_exclude_creator_from_cc_when_creator_equals_submitted_by(
        self, db_session
    ):
        """If creator == submitted_by (IS creates for themselves) and the
        flag is on, CC ends up empty — consistent and non-duplicate."""
        from services.mailer.recipients import resolve_recipients

        out = resolve_recipients(
            db_session,
            creator_email="is@tradingsolutions.com",
            submitted_by_email="IS@tradingsolutions.com",  # case-insensitive match
            exclude_creator_from_cc=True,
        )
        assert out["cc"] == []
