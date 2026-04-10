"""TDD tests for database/crud/clientes.py (SQLAlchemy version).

These tests verify the CRUD functions that manage client requests,
customs registrations, port registrations, and shipping line registrations.
All functions accept a SQLAlchemy session as their first parameter.
"""

from sqlalchemy import text


class TestGetProfileId:
    """Tests for get_profile_id()."""

    def test_get_profile_id_existing(self, db_session, seed_profiles):
        """get_profile_id for 'cliente' should return a valid integer id."""
        from database.crud.clientes import get_profile_id

        result = get_profile_id(db_session, "cliente")
        assert result is not None
        assert isinstance(result, int)
        assert result == seed_profiles["cliente"]

    def test_get_profile_id_nonexistent(self, db_session, seed_profiles):
        """get_profile_id for a name that doesn't exist should return None."""
        from database.crud.clientes import get_profile_id

        result = get_profile_id(db_session, "nonexistent")
        assert result is None


class TestInsertClientRequest:
    """Tests for insert_client_request()."""

    def test_insert_client_request(self, db_session, seed_profiles):
        """insert_client_request should insert a row and return the new id."""
        from database.crud.clientes import insert_client_request

        request_id = insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Acme Corp",
            email="acme@example.com",
            trading="Colombia",
            location="Colombia",
            language="Español",
            reminder_frequency="Una vez por semana",
            operation_type="EXPO",
            commodity="Coffee",
            has_customs=True,
            has_port=False,
            has_shipping_line=False,
            requested_by="Pedro Luis Bruges",
            user_email="test@tradingsolutions.com",
        )

        assert request_id is not None
        assert isinstance(request_id, int)

        # Verify the row exists in the database
        row = db_session.execute(
            text("SELECT company_name, email FROM requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()
        assert row is not None
        assert row[0] == "Acme Corp"
        assert row[1] == "acme@example.com"

    def test_insert_client_request_created_at_auto(self, db_session, seed_profiles):
        """created_at should be automatically set (NOT NULL) after insert."""
        from database.crud.clientes import insert_client_request

        request_id = insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="AutoDate Inc",
            user_email="test@tradingsolutions.com",
        )

        row = db_session.execute(
            text("SELECT created_at FROM requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()
        assert row is not None
        assert row[0] is not None, "created_at should be auto-populated by DEFAULT"


class TestInsertClientRequestIdReliability:
    """Tests for reliable ID retrieval after insert."""

    def test_insert_returns_correct_id_for_multiple_inserts(self, db_session, seed_profiles):
        """Multiple sequential inserts should each return a unique, correct ID."""
        from database.crud.clientes import insert_client_request

        ids = []
        for i in range(5):
            rid = insert_client_request(
                db_session,
                profile_id=seed_profiles["cliente"],
                company_name=f"Company {i}",
                user_email=f"user{i}@test.com",
            )
            ids.append(rid)

        # All IDs should be unique
        assert len(set(ids)) == 5, f"Expected 5 unique IDs, got {ids}"

        # Each ID should match its company
        for i, rid in enumerate(ids):
            row = db_session.execute(
                text("SELECT company_name FROM requests WHERE id = :id"),
                {"id": rid},
            ).fetchone()
            assert row is not None, f"No row found for id={rid}"
            assert row[0] == f"Company {i}", f"ID {rid} has wrong company: {row[0]}"

    def test_insert_returns_positive_integer(self, db_session, seed_profiles):
        """Return value must be a positive integer."""
        from database.crud.clientes import insert_client_request

        rid = insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Positive ID Test",
            user_email="test@test.com",
        )
        assert isinstance(rid, int)
        assert rid > 0


class TestInsertCustomsRegistration:
    """Tests for insert_customs_registration()."""

    def _create_request(self, db_session, seed_profiles):
        """Helper to create a request and return its id."""
        from database.crud.clientes import insert_client_request

        return insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Customs Test Co",
            has_customs=True,
            user_email="test@tradingsolutions.com",
        )

    def test_insert_customs_registration(self, db_session, seed_profiles):
        """insert_customs_registration should insert rows for each customs name."""
        from database.crud.clientes import insert_customs_registration

        request_id = self._create_request(db_session, seed_profiles)
        customs_list = ["CARGOFLASH", "SIAP", "MOVIADUANA"]

        insert_customs_registration(db_session, request_id, customs_list)

        rows = db_session.execute(
            text("SELECT customs_name FROM customs_registration WHERE request_id = :rid"),
            {"rid": request_id},
        ).fetchall()
        names = [r[0] for r in rows]
        assert len(names) == 3
        assert "CARGOFLASH" in names
        assert "SIAP" in names
        assert "MOVIADUANA" in names

    def test_insert_customs_registration_empty(self, db_session, seed_profiles):
        """insert_customs_registration with empty list should do nothing."""
        from database.crud.clientes import insert_customs_registration

        request_id = self._create_request(db_session, seed_profiles)

        insert_customs_registration(db_session, request_id, [])

        rows = db_session.execute(
            text("SELECT id FROM customs_registration WHERE request_id = :rid"),
            {"rid": request_id},
        ).fetchall()
        assert len(rows) == 0


class TestInsertPortRegistration:
    """Tests for insert_port_registration()."""

    def _create_request(self, db_session, seed_profiles):
        """Helper to create a request and return its id."""
        from database.crud.clientes import insert_client_request

        return insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Port Test Co",
            has_port=True,
            user_email="test@tradingsolutions.com",
        )

    def test_insert_port_registration(self, db_session, seed_profiles):
        """insert_port_registration should insert port+terminal rows."""
        from database.crud.clientes import insert_port_registration

        request_id = self._create_request(db_session, seed_profiles)
        ports_dict = {
            "Cartagena": ["COMPAS", "CONTECAR/SPRC"],
            "Buenaventura": ["TCBUEN"],
        }

        insert_port_registration(db_session, request_id, ports_dict)

        rows = db_session.execute(
            text(
                "SELECT port_name, terminal_name FROM port_registration "
                "WHERE request_id = :rid ORDER BY port_name, terminal_name"
            ),
            {"rid": request_id},
        ).fetchall()

        assert len(rows) == 3
        port_terminal_pairs = [(r[0], r[1]) for r in rows]
        assert ("Buenaventura", "TCBUEN") in port_terminal_pairs
        assert ("Cartagena", "COMPAS") in port_terminal_pairs
        assert ("Cartagena", "CONTECAR/SPRC") in port_terminal_pairs


class TestInsertShippingLineRegistration:
    """Tests for insert_shipping_line_registration()."""

    def _create_request(self, db_session, seed_profiles):
        """Helper to create a request and return its id."""
        from database.crud.clientes import insert_client_request

        return insert_client_request(
            db_session,
            profile_id=seed_profiles["cliente"],
            company_name="Shipping Test Co",
            has_shipping_line=True,
            user_email="test@tradingsolutions.com",
        )

    def test_insert_shipping_line_registration(self, db_session, seed_profiles):
        """insert_shipping_line_registration should insert line details."""
        from database.crud.clientes import insert_shipping_line_registration

        request_id = self._create_request(db_session, seed_profiles)
        lines_data = {
            "MSC": {
                "POL": "Cartagena",
                "POD": "Rotterdam",
                "Producto": "Coffee",
                "Tipo de Contenedor": "40' HC",
                "Shipper en BL": "Acme Trading",
            },
            "ONE": {},
        }

        insert_shipping_line_registration(db_session, request_id, lines_data)

        rows = db_session.execute(
            text(
                "SELECT line_name, pol, pod, product, container_type, shipper_bl "
                "FROM shipping_line_registration WHERE request_id = :rid "
                "ORDER BY line_name"
            ),
            {"rid": request_id},
        ).fetchall()

        assert len(rows) == 2

        # Find MSC row
        msc_row = [r for r in rows if r[0] == "MSC"][0]
        assert msc_row[1] == "Cartagena"
        assert msc_row[2] == "Rotterdam"
        assert msc_row[3] == "Coffee"
        assert msc_row[4] == "40' HC"
        assert msc_row[5] == "Acme Trading"

        # Find ONE row (empty details)
        one_row = [r for r in rows if r[0] == "ONE"][0]
        assert one_row[1] is None
        assert one_row[2] is None
