"""Tests for services/mailer/pending.py — payload reconstruction + retry sweep.

These cover the durability fix: a request whose creation notification never
went out (email_notified_at NULL) must be redeliverable from the DB alone, and
the sweep must only touch the mailer era (never the legacy pre-mailer rows).
"""
from __future__ import annotations

from sqlalchemy import text


def _insert_request(db_session, profile_id, *, case_id, company="Acme Corp",
                    email="cliente@example.com", notified=False, **cols):
    """Insert a requests row, optionally already-notified, return its id."""
    base = {
        "profile_id": profile_id,
        "company_name": company,
        "email": email,
        "user_email": "pedro@tradingsolutions.com",
        "case_id": case_id,
    }
    base.update(cols)
    keys = ", ".join(base.keys())
    placeholders = ", ".join(f":{k}" for k in base)
    db_session.execute(
        text(f"INSERT INTO requests ({keys}) VALUES ({placeholders})"), base
    )
    if notified:
        db_session.execute(
            text(
                "UPDATE requests SET email_notified_at = CURRENT_TIMESTAMP "
                "WHERE case_id = :c"
            ),
            {"c": case_id},
        )
    db_session.commit()
    return db_session.execute(
        text("SELECT id FROM requests WHERE case_id = :c"), {"c": case_id}
    ).scalar()


class TestBuildPayloadFromRequest:
    def test_reconstructs_core_and_registration_fields(self, db_session, seed_profiles):
        from services.mailer.pending import build_payload_from_request

        rid = _insert_request(
            db_session,
            seed_profiles["cliente"],
            case_id="C0042",
            company="Globex SA",
            email="ops@globex.com, sales@globex.com",
            commercial="Pedro Bruges",
            trading="Colombia",
            country="Panama",
            language="Español",
            operation_type="EXPO",
            commodity="Café",
            has_customs=1,
            has_port=1,
            has_shipping_line=1,
            notes="Cliente prioritario",
            submitted_by_email="is@tradingsolutions.com",
        )
        db_session.execute(
            text("INSERT INTO customs_registration (request_id, customs_name) "
                 "VALUES (:r, 'SIAP'), (:r, 'CARGOFLASH')"),
            {"r": rid},
        )
        db_session.execute(
            text("INSERT INTO port_registration (request_id, port_name, terminal_name) "
                 "VALUES (:r, 'Cartagena', 'COMPAS')"),
            {"r": rid},
        )
        db_session.execute(
            text("INSERT INTO shipping_line_registration "
                 "(request_id, line_name, pol, pod, product, container_type, shipper_bl) "
                 "VALUES (:r, 'MSC', :pol, :pod, :prod, :ct, :sb)"),
            {"r": rid, "pol": "Cartagena", "pod": "Shanghai", "prod": "Café",
             "ct": "40' HC", "sb": "Globex SA"},
        )
        db_session.commit()

        built = build_payload_from_request(db_session, rid)
        assert built is not None
        assert built["case_id"] == "C0042"
        assert built["creator_email"] == "pedro@tradingsolutions.com"
        assert built["submitted_by_email"] == "is@tradingsolutions.com"

        p = built["payload"]
        assert p["company_name"] == "Globex SA"
        assert p["email"] == "ops@globex.com, sales@globex.com"
        assert p["requested_by"] == "Pedro Bruges"
        assert p["tipo_solicitud"] == "cliente"      # resolved from profiles
        assert p["location"] == "Panama"             # DB column is `country`
        assert p["tipo_operacion"] == "EXPO"
        # registration display strings
        assert "SIAP" in p["aduana"] and "CARGOFLASH" in p["aduana"]
        assert p["puerto"] == "Cartagena"
        assert p["linea_naviera"] == "MSC"
        assert p["pol"] == "Cartagena"
        assert p["pod"] == "Shanghai"
        assert p["tipo_contenedor"] == "40' HC"
        assert p["notes"] == "Cliente prioritario"

    def test_returns_none_for_missing_request(self, db_session, seed_profiles):
        from services.mailer.pending import build_payload_from_request
        assert build_payload_from_request(db_session, 99999) is None


class TestRetryPendingNotifications:
    def test_redelivers_unnotified_in_mailer_era_only(
        self, db_session, seed_profiles, mock_smtp
    ):
        from services.mailer.pending import retry_pending_notifications

        # r1: NOT notified, created BEFORE the mailer era (lowest id).
        r1 = _insert_request(db_session, seed_profiles["cliente"], case_id="C0001")
        # r2: notified -> establishes the mailer-era cutoff (= r2.id).
        r2 = _insert_request(db_session, seed_profiles["cliente"], case_id="C0002",
                             notified=True)
        # r3: NOT notified, in the mailer era (id > cutoff) -> should redeliver.
        r3 = _insert_request(db_session, seed_profiles["cliente"], case_id="C0003")

        tally = retry_pending_notifications(db_session)

        # r3 redelivered; r1 (pre-era) left untouched.
        assert tally["sent"] == 1
        assert mock_smtp["instance_ssl"].send_message.called

        def _notified(rid):
            return db_session.execute(
                text("SELECT email_notified_at FROM requests WHERE id = :id"),
                {"id": rid},
            ).scalar()

        assert _notified(r3) is not None      # redelivered + marked
        assert _notified(r1) is None          # pre-mailer-era: never touched
        assert _notified(r2) is not None      # already notified, unchanged

    def test_noop_when_nothing_ever_notified(self, db_session, seed_profiles, mock_smtp):
        from services.mailer.pending import retry_pending_notifications

        # No notified rows at all -> no mailer era -> must not touch legacy rows.
        _insert_request(db_session, seed_profiles["cliente"], case_id="C0001")
        tally = retry_pending_notifications(db_session)
        assert tally == {"attempted": 0, "sent": 0, "skipped": 0, "failed": 0}
        assert not mock_smtp["instance_ssl"].send_message.called

    def test_idempotent_skips_already_notified(self, db_session, seed_profiles, mock_smtp):
        from services.mailer.pending import retry_pending_notifications

        _insert_request(db_session, seed_profiles["cliente"], case_id="C0002",
                        notified=True)
        # Only notified rows exist -> nothing to redeliver.
        tally = retry_pending_notifications(db_session)
        assert tally["sent"] == 0
        assert not mock_smtp["instance_ssl"].send_message.called
