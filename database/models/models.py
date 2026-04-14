"""SQLAlchemy 2.0-style ORM models for the compliance platform.

Each model mirrors one table from init_db.sql.  Column types, nullability,
defaults, and foreign keys match the production PostgreSQL schema.
"""

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base


# ===================================================================
# 1. profiles
# ===================================================================

class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    document_types: Mapped[List["DocumentType"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan",
    )
    requests: Mapped[List["Request"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan",
    )


# ===================================================================
# 2. status
# ===================================================================

class Status(Base):
    __tablename__ = "status"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(100), nullable=False)


# ===================================================================
# 3. document_type
# ===================================================================

class DocumentType(Base):
    __tablename__ = "document_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False,
    )
    category: Mapped[str] = mapped_column(String(150), nullable=False)

    # Relationships
    profile: Mapped["Profile"] = relationship(back_populates="document_types")
    registrations: Mapped[List["Registration"]] = relationship(
        back_populates="document_type", cascade="all, delete-orphan",
    )


# ===================================================================
# 4. requests
# ===================================================================

class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False,
    )
    commercial: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    trading: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reminder_frequency: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )
    operation_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    commodity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customs_req: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_customs: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    has_port: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    has_shipping_line: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0",
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True,
    )
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Migration 003 additions
    submitted_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    case_id: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, unique=True)
    reminder_max_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    profile: Mapped["Profile"] = relationship(back_populates="requests")
    comments: Mapped[List["Comment"]] = relationship(
        back_populates="request", cascade="all, delete-orphan",
    )
    registrations: Mapped[List["Registration"]] = relationship(
        back_populates="request", cascade="all, delete-orphan",
    )
    customs_registrations: Mapped[List["CustomsRegistration"]] = relationship(
        back_populates="request", cascade="all, delete-orphan",
    )
    port_registrations: Mapped[List["PortRegistration"]] = relationship(
        back_populates="request", cascade="all, delete-orphan",
    )
    shipping_line_registrations: Mapped[List["ShippingLineRegistration"]] = relationship(
        back_populates="request", cascade="all, delete-orphan",
    )
    internal_registrations: Mapped[List["InternalRegistration"]] = relationship(
        back_populates="request", cascade="all, delete-orphan",
    )


# ===================================================================
# 5. comments
# ===================================================================

class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notifications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    request: Mapped["Request"] = relationship(back_populates="comments")
    registrations: Mapped[List["Registration"]] = relationship(
        back_populates="comment",
    )


# ===================================================================
# 6. registration
# ===================================================================

class Registration(Base):
    __tablename__ = "registration"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    doc_type_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("document_type.id", ondelete="CASCADE"), nullable=True,
    )
    id_comments: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("comments.id"), nullable=True,
    )
    status_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("status.id"), nullable=True,
    )
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    drive_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True,
    )
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    razon_social: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    fecha_creacion: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Relationships
    request: Mapped["Request"] = relationship(back_populates="registrations")
    document_type: Mapped[Optional["DocumentType"]] = relationship(
        back_populates="registrations",
    )
    comment: Mapped[Optional["Comment"]] = relationship(
        back_populates="registrations",
    )
    status: Mapped[Optional["Status"]] = relationship()


# ===================================================================
# 7. customs_registration
# ===================================================================

class CustomsRegistration(Base):
    __tablename__ = "customs_registration"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    customs_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("status.id", ondelete="SET NULL"), nullable=True,
    )

    # Relationships
    request: Mapped["Request"] = relationship(back_populates="customs_registrations")
    status: Mapped[Optional["Status"]] = relationship()


# ===================================================================
# 8. port_registration
# ===================================================================

class PortRegistration(Base):
    __tablename__ = "port_registration"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    port_name: Mapped[str] = mapped_column(String(150), nullable=False)
    terminal_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    status_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("status.id", ondelete="SET NULL"), nullable=True,
    )

    # Relationships
    request: Mapped["Request"] = relationship(back_populates="port_registrations")
    status: Mapped[Optional["Status"]] = relationship()


# ===================================================================
# 9. shipping_line_registration
# ===================================================================

class ShippingLineRegistration(Base):
    __tablename__ = "shipping_line_registration"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    line_name: Mapped[str] = mapped_column(String(150), nullable=False)
    pol: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    pod: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    product: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    container_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    shipper_bl: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("status.id", ondelete="SET NULL"), nullable=True,
    )

    # Relationships
    request: Mapped["Request"] = relationship(
        back_populates="shipping_line_registrations",
    )
    status: Mapped[Optional["Status"]] = relationship()


# ===================================================================
# 10. internal_registration
# ===================================================================

class InternalRegistration(Base):
    __tablename__ = "internal_registration"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    internal_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("status.id"), nullable=True,
    )

    # Relationships
    request: Mapped["Request"] = relationship(
        back_populates="internal_registrations",
    )
    status: Mapped[Optional["Status"]] = relationship()


# ===================================================================
# 11. comment_entries
# ===================================================================

class CommentEntry(Base):
    __tablename__ = "comment_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    author_email: Mapped[str] = mapped_column(String(255), nullable=False)
    author_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(50), default="comment")
    image_drive_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True,
    )

    # Relationships
    request: Mapped["Request"] = relationship()


# ===================================================================
# 12. notifications
# ===================================================================

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True,
    )

    # Relationships
    request: Mapped[Optional["Request"]] = relationship()


# ===================================================================
# 13. audit_log
# ===================================================================

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(50))  # CREATE, UPDATE, DELETE, UPLOAD, STATUS_CHANGE
    entity_type: Mapped[str] = mapped_column(String(100))  # request, registration, customs, port, shipping_line
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ===================================================================
# 14. users (migration 003)
# ===================================================================

class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    nombre_display: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)  # comercial | inside_sales | compliance | otro
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True,
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


# ===================================================================
# 15. inside_sales_comerciales (migration 003, many-to-many)
# ===================================================================

class InsideSalesComercial(Base):
    __tablename__ = "inside_sales_comerciales"

    inside_sales_email: Mapped[str] = mapped_column(
        String(255), ForeignKey("users.email", ondelete="CASCADE"), primary_key=True,
    )
    comercial_email: Mapped[str] = mapped_column(
        String(255), ForeignKey("users.email", ondelete="CASCADE"), primary_key=True,
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True,
    )
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


# ===================================================================
# 16. request_attachments (migration 003)
# ===================================================================

class RequestAttachment(Base):
    __tablename__ = "request_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    drive_link: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True,
    )


# ===================================================================
# 17. reminder_schedule (migration 003)
# ===================================================================

class ReminderSchedule(Base):
    __tablename__ = "reminder_schedule"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False,
    )
    next_reminder_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    frequency_days: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True,
    )
