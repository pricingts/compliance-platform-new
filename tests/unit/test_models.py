"""TDD tests for SQLAlchemy ORM models (Phase 2A).

Tests are written BEFORE model implementation following Test-Driven Development.
Each test verifies that the ORM model mirrors the database schema defined in
init_db.sql, including column types, nullability, defaults, foreign keys,
and relationships.
"""

import pytest
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Fixture: ORM-backed in-memory session
# ---------------------------------------------------------------------------

@pytest.fixture
def orm_session():
    """Session backed by ORM models instead of raw SQL.

    Creates tables from Base.metadata (the ORM models) rather than from
    the raw DDL in conftest._SCHEMA_SQL.  This proves the models themselves
    can produce a valid schema.
    """
    from database.models.base import Base
    # Import all models so they are registered with Base.metadata
    import database.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ===================================================================
# Profile model
# ===================================================================

class TestProfileModel:

    def test_profile_create_and_query(self, orm_session):
        """Create a Profile row via ORM and query it back."""
        from database.models import Profile

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        result = orm_session.query(Profile).filter_by(name="cliente").first()
        assert result is not None
        assert result.id is not None
        assert result.name == "cliente"

    def test_profile_name_not_nullable(self, orm_session):
        """Profile.name is NOT NULL -- inserting without it should raise."""
        from database.models import Profile

        profile = Profile()  # name not set
        orm_session.add(profile)
        with pytest.raises(Exception):
            orm_session.commit()
        orm_session.rollback()


# ===================================================================
# Status model
# ===================================================================

class TestStatusModel:

    def test_status_create_and_query(self, orm_session):
        """Create a Status row via ORM and query it back."""
        from database.models import Status

        status = Status(status="pendiente")
        orm_session.add(status)
        orm_session.commit()

        result = orm_session.query(Status).filter_by(status="pendiente").first()
        assert result is not None
        assert result.id is not None
        assert result.status == "pendiente"


# ===================================================================
# DocumentType model
# ===================================================================

class TestDocumentTypeModel:

    def test_document_type_with_profile_relationship(self, orm_session):
        """DocumentType should FK to Profile and expose a relationship."""
        from database.models import Profile, DocumentType

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        doc_type = DocumentType(profile_id=profile.id, category="factura")
        orm_session.add(doc_type)
        orm_session.commit()

        result = orm_session.query(DocumentType).first()
        assert result is not None
        assert result.profile_id == profile.id
        assert result.category == "factura"

        # Verify the relationship navigates back to Profile
        assert result.profile is not None
        assert result.profile.name == "cliente"

        # Verify the reverse relationship on Profile
        assert len(profile.document_types) == 1
        assert profile.document_types[0].category == "factura"


# ===================================================================
# Request model
# ===================================================================

class TestRequestModel:

    def test_request_create_with_defaults(self, orm_session):
        """Request should auto-populate created_at and boolean defaults."""
        from database.models import Profile, Request

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(
            profile_id=profile.id,
            company_name="Acme Corp",
            email="acme@example.com",
        )
        orm_session.add(request)
        orm_session.commit()

        result = orm_session.query(Request).first()
        assert result is not None
        assert result.company_name == "Acme Corp"
        # created_at should have a default value
        assert result.created_at is not None
        # Boolean fields should default to False
        assert result.has_customs is False
        assert result.has_port is False
        assert result.has_shipping_line is False

    def test_request_profile_relationship(self, orm_session):
        """Request.profile should navigate to the parent Profile."""
        from database.models import Profile, Request

        profile = Profile(name="proveedor")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id, company_name="Supplier Inc")
        orm_session.add(request)
        orm_session.commit()

        result = orm_session.query(Request).first()
        assert result.profile is not None
        assert result.profile.name == "proveedor"

        # Reverse relationship
        assert len(profile.requests) == 1
        assert profile.requests[0].company_name == "Supplier Inc"

    def test_request_nullable_fields(self, orm_session):
        """Optional Request fields should accept None."""
        from database.models import Profile, Request

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id)
        orm_session.add(request)
        orm_session.commit()

        result = orm_session.query(Request).first()
        assert result.commercial is None
        assert result.company_name is None
        assert result.trading is None
        assert result.country is None
        assert result.language is None
        assert result.email is None
        assert result.commodity is None
        assert result.customs_req is None
        assert result.user_email is None


# ===================================================================
# Comment model
# ===================================================================

class TestCommentModel:

    def test_comment_request_relationship(self, orm_session):
        """Comment should FK to Request and expose a relationship."""
        from database.models import Profile, Request, Comment

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id, company_name="Test Co")
        orm_session.add(request)
        orm_session.commit()

        comment = Comment(
            request_id=request.id,
            comments="Documentos pendientes",
            notifications="email enviado",
        )
        orm_session.add(comment)
        orm_session.commit()

        result = orm_session.query(Comment).first()
        assert result is not None
        assert result.comments == "Documentos pendientes"
        assert result.notifications == "email enviado"
        assert result.request is not None
        assert result.request.company_name == "Test Co"

        # Reverse from Request
        assert len(request.comments) == 1


# ===================================================================
# Registration model
# ===================================================================

class TestRegistrationModel:

    def test_registration_relationships(self, orm_session):
        """Registration should FK to request, doc_type, comments, and status."""
        from database.models import (
            Profile, Request, DocumentType, Comment, Status, Registration,
        )

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id, company_name="Reg Co")
        orm_session.add(request)
        orm_session.commit()

        doc_type = DocumentType(profile_id=profile.id, category="contrato")
        orm_session.add(doc_type)
        orm_session.commit()

        comment = Comment(request_id=request.id, comments="ok")
        orm_session.add(comment)
        orm_session.commit()

        status = Status(status="aprobado")
        orm_session.add(status)
        orm_session.commit()

        reg = Registration(
            request_id=request.id,
            doc_type_id=doc_type.id,
            id_comments=comment.id,
            status_id=status.id,
            file_name="contract.pdf",
            drive_link="https://drive.google.com/file/abc",
            uploaded_by="admin@test.com",
            razon_social="Acme SAS",
            fecha_creacion=date(2025, 1, 15),
        )
        orm_session.add(reg)
        orm_session.commit()

        result = orm_session.query(Registration).first()
        assert result is not None
        assert result.file_name == "contract.pdf"
        assert result.uploaded_at is not None  # default timestamp
        assert result.razon_social == "Acme SAS"
        assert result.fecha_creacion == date(2025, 1, 15)

        # Relationships
        assert result.request.company_name == "Reg Co"
        assert result.document_type.category == "contrato"
        assert result.comment.comments == "ok"
        assert result.status.status == "aprobado"

    def test_registration_nullable_fks(self, orm_session):
        """doc_type_id, id_comments, and status_id are nullable."""
        from database.models import Profile, Request, Registration

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id)
        orm_session.add(request)
        orm_session.commit()

        reg = Registration(request_id=request.id, file_name="doc.pdf")
        orm_session.add(reg)
        orm_session.commit()

        result = orm_session.query(Registration).first()
        assert result.doc_type_id is None
        assert result.id_comments is None
        assert result.status_id is None


# ===================================================================
# CustomsRegistration model
# ===================================================================

class TestCustomsRegistrationModel:

    def test_customs_registration_create(self, orm_session):
        """Create a CustomsRegistration and verify fields."""
        from database.models import Profile, Request, Status, CustomsRegistration

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id, has_customs=True)
        orm_session.add(request)
        orm_session.commit()

        status = Status(status="pendiente")
        orm_session.add(status)
        orm_session.commit()

        cr = CustomsRegistration(
            request_id=request.id,
            customs_name="CARGOFLASH",
            status_id=status.id,
        )
        orm_session.add(cr)
        orm_session.commit()

        result = orm_session.query(CustomsRegistration).first()
        assert result is not None
        assert result.customs_name == "CARGOFLASH"
        assert result.request.id == request.id
        assert result.status.status == "pendiente"

    def test_customs_registration_status_nullable(self, orm_session):
        """status_id is nullable on customs_registration."""
        from database.models import Profile, Request, CustomsRegistration

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id)
        orm_session.add(request)
        orm_session.commit()

        cr = CustomsRegistration(request_id=request.id, customs_name="SIAP")
        orm_session.add(cr)
        orm_session.commit()

        result = orm_session.query(CustomsRegistration).first()
        assert result.status_id is None


# ===================================================================
# PortRegistration model
# ===================================================================

class TestPortRegistrationModel:

    def test_port_registration_create(self, orm_session):
        """Create a PortRegistration and verify fields."""
        from database.models import Profile, Request, Status, PortRegistration

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id, has_port=True)
        orm_session.add(request)
        orm_session.commit()

        status = Status(status="aprobado")
        orm_session.add(status)
        orm_session.commit()

        pr = PortRegistration(
            request_id=request.id,
            port_name="Cartagena",
            terminal_name="CONTECAR",
            status_id=status.id,
        )
        orm_session.add(pr)
        orm_session.commit()

        result = orm_session.query(PortRegistration).first()
        assert result is not None
        assert result.port_name == "Cartagena"
        assert result.terminal_name == "CONTECAR"
        assert result.request.id == request.id
        assert result.status.status == "aprobado"

    def test_port_registration_terminal_nullable(self, orm_session):
        """terminal_name and status_id are nullable."""
        from database.models import Profile, Request, PortRegistration

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id)
        orm_session.add(request)
        orm_session.commit()

        pr = PortRegistration(request_id=request.id, port_name="Buenaventura")
        orm_session.add(pr)
        orm_session.commit()

        result = orm_session.query(PortRegistration).first()
        assert result.terminal_name is None
        assert result.status_id is None


# ===================================================================
# ShippingLineRegistration model
# ===================================================================

class TestShippingLineRegistrationModel:

    def test_shipping_line_registration_create(self, orm_session):
        """Create a ShippingLineRegistration and verify all fields."""
        from database.models import (
            Profile, Request, Status, ShippingLineRegistration,
        )

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id, has_shipping_line=True)
        orm_session.add(request)
        orm_session.commit()

        status = Status(status="en revision")
        orm_session.add(status)
        orm_session.commit()

        sl = ShippingLineRegistration(
            request_id=request.id,
            line_name="MSC",
            pol="Cartagena",
            pod="Rotterdam",
            product="Coffee",
            container_type="40' HC",
            shipper_bl="Acme Trading",
            status_id=status.id,
        )
        orm_session.add(sl)
        orm_session.commit()

        result = orm_session.query(ShippingLineRegistration).first()
        assert result is not None
        assert result.line_name == "MSC"
        assert result.pol == "Cartagena"
        assert result.pod == "Rotterdam"
        assert result.product == "Coffee"
        assert result.container_type == "40' HC"
        assert result.shipper_bl == "Acme Trading"
        assert result.request.id == request.id
        assert result.status.status == "en revision"

    def test_shipping_line_optional_fields(self, orm_session):
        """pol, pod, product, container_type, shipper_bl, status_id are nullable."""
        from database.models import Profile, Request, ShippingLineRegistration

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id)
        orm_session.add(request)
        orm_session.commit()

        sl = ShippingLineRegistration(
            request_id=request.id, line_name="ONE",
        )
        orm_session.add(sl)
        orm_session.commit()

        result = orm_session.query(ShippingLineRegistration).first()
        assert result.pol is None
        assert result.pod is None
        assert result.product is None
        assert result.container_type is None
        assert result.shipper_bl is None
        assert result.status_id is None


# ===================================================================
# InternalRegistration model
# ===================================================================

class TestInternalRegistrationModel:

    def test_internal_registration_create(self, orm_session):
        """Create an InternalRegistration and verify fields."""
        from database.models import Profile, Request, Status, InternalRegistration

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id)
        orm_session.add(request)
        orm_session.commit()

        status = Status(status="pendiente")
        orm_session.add(status)
        orm_session.commit()

        ir = InternalRegistration(
            request_id=request.id,
            internal_label="Internal Review",
            status_id=status.id,
        )
        orm_session.add(ir)
        orm_session.commit()

        result = orm_session.query(InternalRegistration).first()
        assert result is not None
        assert result.internal_label == "Internal Review"
        assert result.request.id == request.id
        assert result.status.status == "pendiente"

    def test_internal_registration_nullable_fields(self, orm_session):
        """internal_label and status_id are nullable."""
        from database.models import Profile, Request, InternalRegistration

        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(profile_id=profile.id)
        orm_session.add(request)
        orm_session.commit()

        ir = InternalRegistration(request_id=request.id)
        orm_session.add(ir)
        orm_session.commit()

        result = orm_session.query(InternalRegistration).first()
        assert result.internal_label is None
        assert result.status_id is None


# ===================================================================
# Cascade delete behaviour
# ===================================================================

class TestCascadeDelete:

    def test_cascade_delete_request_deletes_children(self, orm_session):
        """Deleting a Request should cascade-delete comments, customs,
        port, shipping line, registration, and internal registration rows."""
        from database.models import (
            Profile, Request, Comment, Registration,
            CustomsRegistration, PortRegistration,
            ShippingLineRegistration, InternalRegistration,
        )

        # Setup
        profile = Profile(name="cliente")
        orm_session.add(profile)
        orm_session.commit()

        request = Request(
            profile_id=profile.id,
            company_name="Cascade Co",
            has_customs=True,
            has_port=True,
            has_shipping_line=True,
        )
        orm_session.add(request)
        orm_session.commit()

        # Create child records
        comment = Comment(request_id=request.id, comments="test comment")
        orm_session.add(comment)
        orm_session.commit()

        reg = Registration(request_id=request.id, file_name="test.pdf")
        orm_session.add(reg)

        customs = CustomsRegistration(
            request_id=request.id, customs_name="CARGOFLASH",
        )
        orm_session.add(customs)

        port = PortRegistration(
            request_id=request.id, port_name="Cartagena",
        )
        orm_session.add(port)

        shipping = ShippingLineRegistration(
            request_id=request.id, line_name="MSC",
        )
        orm_session.add(shipping)

        internal = InternalRegistration(
            request_id=request.id, internal_label="review",
        )
        orm_session.add(internal)
        orm_session.commit()

        # Verify children exist
        assert orm_session.query(Comment).count() == 1
        assert orm_session.query(Registration).count() == 1
        assert orm_session.query(CustomsRegistration).count() == 1
        assert orm_session.query(PortRegistration).count() == 1
        assert orm_session.query(ShippingLineRegistration).count() == 1
        assert orm_session.query(InternalRegistration).count() == 1

        # Delete the request
        orm_session.delete(request)
        orm_session.commit()

        # All children should be gone
        assert orm_session.query(Comment).count() == 0
        assert orm_session.query(Registration).count() == 0
        assert orm_session.query(CustomsRegistration).count() == 0
        assert orm_session.query(PortRegistration).count() == 0
        assert orm_session.query(ShippingLineRegistration).count() == 0
        assert orm_session.query(InternalRegistration).count() == 0

        # The profile should still exist (not cascaded)
        assert orm_session.query(Profile).count() == 1
