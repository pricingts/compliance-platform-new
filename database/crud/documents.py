# database/crud/documents.py
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from typing import Optional

from services.audit import log_action

# ==========================
# 🔹 EMPRESAS Y PERFILES
# ==========================

def get_all_company_names(session: Session) -> list[str]:
    rows = session.execute(
        text("SELECT DISTINCT company_name FROM requests ORDER BY company_name ASC")
    ).fetchall()
    return [r[0] for r in rows if r[0]]

def get_profiles_list(session: Session) -> list[str]:
    rows = session.execute(
        text("SELECT name FROM profiles ORDER BY name ASC")
    ).fetchall()
    return [r[0] for r in rows if r[0]]

def get_profile_id_by_name(session: Session, profile_name: str) -> Optional[int]:
    return session.execute(
        text("SELECT id FROM profiles WHERE name = :n"),
        {"n": profile_name}
    ).scalar()

# ==========================
# 🔹 SOLICITUDES EXISTENTES
# ==========================

def get_requests_by_company_and_profile(session: Session, company_name: str, profile_id: int, limit: int = 20) -> list[dict]:
    rows = session.execute(
        text("""
            SELECT id, COALESCE(created_at, CURRENT_TIMESTAMP) AS created_at
            FROM requests
            WHERE company_name = :company_name AND profile_id = :profile_id
            ORDER BY id DESC
            LIMIT :limit
        """),
        {"company_name": company_name, "profile_id": profile_id, "limit": limit}
    ).mappings().all()
    return rows

# ==========================
# 🔹 TIPOS DE DOCUMENTOS
# ==========================

def get_required_document_types(session: Session, profile_id: int) -> list[dict]:
    """
    Devuelve los tipos de documentos (category) requeridos para un perfil.
    """
    rows = session.execute(
        text("""
            SELECT id, category AS name
            FROM document_type
            WHERE profile_id = :pid
            ORDER BY category ASC
        """),
        {"pid": profile_id}
    ).mappings().all()
    return rows

# ==========================
# 🔹 DOCUMENTOS SUBIDOS
# ==========================

def get_uploaded_documents_map(session: Session, request_id: int) -> dict[int, list[dict]]:
    rows = session.execute(
        text("""
            SELECT id, doc_type_id, file_name, drive_link, uploaded_at, uploaded_by
            FROM registration
            WHERE request_id = :rid
            ORDER BY uploaded_at DESC
        """),
        {"rid": request_id}
    ).mappings().all()

    grouped = {}
    for r in rows:
        doc_type = r["doc_type_id"]
        grouped.setdefault(doc_type, []).append(dict(r))  # 🔹 Asegura que cada elemento sea un dict real
    return grouped


def upsert_uploaded_document(
    session: Session,
    request_id: int,
    document_type_id: int,
    file_name: str,
    drive_link: str,
    uploaded_by: str,
    razon_social: Optional[str] = None,
    fecha_creacion: Optional[datetime] = None,
    user_email: Optional[str] = None,
) -> None:
    session.execute(
        text("""
            INSERT INTO registration (request_id, doc_type_id, file_name, drive_link, uploaded_by, razon_social, fecha_creacion)
            VALUES (:request_id, :doc_type_id, :file_name, :drive_link, :uploaded_by, :razon_social, :fecha_creacion)
        """),
        {
            "request_id": request_id,
            "doc_type_id": document_type_id,
            "file_name": file_name,
            "drive_link": drive_link,
            "uploaded_by": uploaded_by,
            "razon_social": razon_social,
            "fecha_creacion": fecha_creacion
        }
    )

    if user_email:
        log_action(
            session=session,
            user_email=user_email,
            action="UPLOAD",
            entity_type="registration",
            entity_id=request_id,
            new_value={"file_name": file_name, "doc_type_id": document_type_id},
            details=f"Request #{request_id}: uploaded {file_name}",
        )


def get_request_meta(session: Session, request_id: int) -> dict:
    row = session.execute(
        text("""
            SELECT notifications, comments
            FROM comments
            WHERE request_id = :rid
        """),
        {"rid": request_id}
    ).one_or_none()

    if not row:
        return {}
    return {
        "notification_followup": row[0],
        "general_comments": row[1],
    }

def update_request_meta(session: Session, request_id: int, notifications: str, comments: str) -> None:
    existing = session.execute(
        text("SELECT id FROM comments WHERE request_id = :rid"),
        {"rid": request_id}
    ).fetchone()

    if existing:
        session.execute(
            text("""
                UPDATE comments
                SET notifications = :notifications,
                    comments = :comments
                WHERE request_id = :rid
            """),
            {"rid": request_id, "notifications": notifications, "comments": comments}
        )
    else:
        session.execute(
            text("""
                INSERT INTO comments (request_id, notifications, comments)
                VALUES (:rid, :notifications, :comments)
            """),
            {"rid": request_id, "notifications": notifications, "comments": comments}
        )

def get_all_statuses(session: Session) -> dict[str, int]:
    rows = session.execute(text("SELECT id, status FROM status ORDER BY id")).fetchall()
    return {r[1]: r[0] for r in rows}


def get_shipping_lines_status(session: Session, request_id: int) -> list:
    return session.execute(text("""
        SELECT id, line_name, status_id,
               pol, pod, product, container_type, shipper_bl
        FROM shipping_line_registration
        WHERE request_id = :req
    """), {"req": request_id}).fetchall()

def get_ports_status(session: Session, request_id: int) -> list:
    return session.execute(text("""
        SELECT id, port_name, terminal_name, status_id
        FROM port_registration
        WHERE request_id = :req
    """), {"req": request_id}).fetchall()

def get_customs_status(session: Session, request_id: int) -> list:
    return session.execute(text("""
        SELECT id, customs_name, status_id
        FROM customs_registration
        WHERE request_id = :req
    """), {"req": request_id}).fetchall()


def upsert_status(
    session: Session,
    table_name: str,
    request_id: int,
    entity_name: str,
    status_id: int,
    terminal_name: Optional[str] = None,
    user_email: Optional[str] = None,
) -> None:
    valid_tables = {
        "shipping_line_registration": ("line_name", None),
        "port_registration": ("port_name", "terminal_name"),
        "customs_registration": ("customs_name", None),
        "internal_registration": ("internal_label", None),
    }

    if table_name not in valid_tables:
        raise ValueError(f"Invalid table name: {table_name}")

    name_field, terminal_field = valid_tables[table_name]
    params = {
        "request_id": request_id,
        "name": entity_name.strip() if entity_name else "",
        "status_id": status_id,
    }

    old_status_id = None
    record_id = None

    if terminal_field:
        terminal_clean = terminal_name.strip() if terminal_name else None
        params["terminal_name"] = terminal_clean

        existing = session.execute(
            text(f"""
                SELECT id, status_id FROM {table_name}
                WHERE request_id = :request_id
                AND {name_field} = :name
                AND (
                        ({terminal_field} IS NULL AND :terminal_name IS NULL)
                    OR {terminal_field} = :terminal_name
                    OR (COALESCE({terminal_field}, '') = COALESCE(:terminal_name, ''))
                )
            """),
            params
        ).fetchone()

        if existing:
            record_id = existing[0]
            old_status_id = existing[1]
            session.execute(
                text(f"UPDATE {table_name} SET status_id = :status_id WHERE id = :id"),
                {"status_id": status_id, "id": record_id},
            )
        else:
            session.execute(
                text(f"""
                    INSERT INTO {table_name} (request_id, {name_field}, {terminal_field}, status_id)
                    VALUES (:request_id, :name, :terminal_name, :status_id)
                """),
                params
            )

    else:
        existing = session.execute(
            text(f"""
                SELECT id, status_id FROM {table_name}
                WHERE request_id = :request_id
                AND {name_field} = :name
            """),
            params
        ).fetchone()

        if existing:
            record_id = existing[0]
            old_status_id = existing[1]
            session.execute(
                text(f"UPDATE {table_name} SET status_id = :status_id WHERE id = :id"),
                {"status_id": status_id, "id": record_id},
            )
        else:
            session.execute(
                text(f"""
                    INSERT INTO {table_name} (request_id, {name_field}, status_id)
                    VALUES (:request_id, :name, :status_id)
                """),
                params
            )

    # --- Audit: log status change if status actually changed ---
    if user_email and old_status_id is not None and old_status_id != status_id:
        entity_label = entity_name
        if terminal_name:
            entity_label = f"{entity_name} / {terminal_name}"
        log_action(
            session=session,
            user_email=user_email,
            action="STATUS_CHANGE",
            entity_type=table_name,
            entity_id=record_id,
            old_value={"status_id": old_status_id, "entity": entity_label},
            new_value={"status_id": status_id, "entity": entity_label},
            details=f"Request #{request_id}: {entity_label}",
        )

        # --- Notify the request owner about status change (A2) ---
        request_owner = session.execute(
            text("SELECT user_email, company_name FROM requests WHERE id = :rid"),
            {"rid": request_id},
        ).fetchone()
        if request_owner and request_owner.user_email and request_owner.user_email != user_email:
            # Resolve status names for the notification message
            old_name = session.execute(
                text("SELECT status FROM status WHERE id = :sid"),
                {"sid": old_status_id},
            ).scalar() or "sin estado"
            new_name = session.execute(
                text("SELECT status FROM status WHERE id = :sid"),
                {"sid": status_id},
            ).scalar() or "sin estado"

            insert_notification(
                session=session,
                user_email=request_owner.user_email,
                request_id=request_id,
                message=f"{entity_label} cambio de '{old_name}' a '{new_name}' ({request_owner.company_name or 'solicitud'})",
            )

def batch_upsert_statuses(
    session: Session,
    updates: list[dict],
    user_email: Optional[str] = None,
) -> None:
    """Batch upsert status updates in a single transaction.

    Each item in `updates` must have:
        - table_name: str (e.g., "shipping_line_registration")
        - request_id: int
        - entity_name: str
        - status_id: int
        - terminal_name: str | None (only for port_registration)
    """
    for item in updates:
        upsert_status(
            session=session,
            table_name=item["table_name"],
            request_id=item["request_id"],
            entity_name=item["entity_name"],
            status_id=item["status_id"],
            terminal_name=item.get("terminal_name"),
            user_email=item.get("user_email") or user_email,
        )


def get_internal_status(session: Session, request_id: int) -> Optional[int]:
    row = session.execute(
        text("SELECT status_id FROM internal_registration WHERE request_id = :rid"),
        {"rid": request_id}
    ).fetchone()
    return row[0] if row else None

def get_request_creation_date(session: Session, request_id: int) -> Optional[datetime]:
    row = session.execute(
        text("SELECT fecha_creacion FROM registration WHERE request_id = :rid LIMIT 1"),
        {"rid": request_id}
    ).fetchone()
    return row[0] if row else None

def get_comments_by_request(session: Session, request_id: int) -> Optional[dict]:
    result = session.execute(
        text("""
            SELECT comments, notifications
            FROM comments
            WHERE request_id = :request_id
        """),
        {"request_id": request_id}
    ).fetchone()

    if result:
        return {"comments": result[0], "notifications": result[1]}
    return None

def upsert_request_info(
    session: Session,
    request_id: int,
    uploaded_by: str,
    razon_social: Optional[str] = None,
    fecha_creacion: Optional[datetime] = None
) -> None:
    """
    Asegura que la solicitud tenga registrada la razón social y la fecha de creación,
    incluso si no se han subido documentos.

    Si ya existe al menos un registro en 'registration' para la solicitud,
    se actualizan esos campos. Si no existe ninguno, se inserta una fila mínima.
    """
    existing_row = session.execute(
        text("SELECT id FROM registration WHERE request_id = :rid LIMIT 1"),
        {"rid": request_id}
    ).fetchone()

    params = {
        "rid": request_id,
        "uploaded_by": uploaded_by,
        "razon_social": razon_social,
        "fecha_creacion": fecha_creacion
    }

    if existing_row:
        session.execute(
            text("""
                UPDATE registration
                SET razon_social = :razon_social,
                    fecha_creacion = :fecha_creacion
                WHERE request_id = :rid
            """),
            params
        )
    else:
        session.execute(
            text("""
                INSERT INTO registration (
                    request_id, file_name, uploaded_by, razon_social, fecha_creacion
                )
                VALUES (:rid, '-', :uploaded_by, :razon_social, :fecha_creacion)
            """),
            params
        )

def get_razon_social_by_request(session: Session, request_id: int) -> Optional[dict]:
    result = session.execute(
        text("""
            SELECT razon_social, fecha_creacion
            FROM registration
            WHERE request_id = :rid
            LIMIT 1
        """),
        {"rid": request_id}
    ).fetchone()

    if result:
        razon_social = result[0]
        fecha_creacion = result[1]
        return {
            "razon_social": razon_social or None,
            "fecha_creacion": fecha_creacion or None
        }

    return None

def get_requests_for_progress(
    session: Session,
    only_for_email: Optional[str] = None,
    page: int = 0,
    page_size: int = 20,
    search_term: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Return paginated requests and total count, with optional search."""
    search_filter = ""
    params: dict = {
        "email": only_for_email,
        "limit": page_size,
        "offset": page * page_size,
    }

    if search_term:
        search_filter = """
            AND (
                LOWER(company_name) LIKE :search
                OR CAST(id AS VARCHAR) LIKE :search_raw
                OR LOWER(COALESCE(user_email, '')) LIKE :search
            )
        """
        params["search"] = f"%{search_term.lower().strip()}%"
        params["search_raw"] = f"%{search_term.strip()}%"

    count_sql = text(f"""
        SELECT COUNT(*)
        FROM requests
        WHERE (:email IS NULL OR LOWER(user_email) = LOWER(:email))
        {search_filter}
    """)
    total = session.execute(count_sql, params).scalar()

    sql = text(f"""
        SELECT id, company_name, profile_id, created_at, user_email, notes
        FROM requests
        WHERE (:email IS NULL OR LOWER(user_email) = LOWER(:email))
        {search_filter}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = session.execute(sql, params).fetchall()

    results = [
        {
            "id": r.id,
            "company_name": r.company_name,
            "profile_id": r.profile_id,
            "created_at": r.created_at,
            "user_email": r.user_email,
            "notes": r.notes,
        }
        for r in rows
    ]
    return results, total


# ==========================
# COMMENT ENTRIES (threaded)
# ==========================

def insert_comment_entry(
    session: Session,
    request_id: int,
    author_email: str,
    author_name: str,
    content: str,
    entry_type: str = "comment",
    image_drive_link: Optional[str] = None,
    image_file_name: Optional[str] = None,
) -> int:
    """Insert a new comment entry and return its id."""
    params = {
        "request_id": request_id,
        "author_email": author_email,
        "author_name": author_name,
        "content": content,
        "entry_type": entry_type,
        "image_drive_link": image_drive_link,
        "image_file_name": image_file_name,
    }

    dialect = session.bind.dialect.name if session.bind else "unknown"

    if dialect == "postgresql":
        result = session.execute(
            text("""
                INSERT INTO comment_entries
                    (request_id, author_email, author_name, content, entry_type,
                     image_drive_link, image_file_name)
                VALUES
                    (:request_id, :author_email, :author_name, :content, :entry_type,
                     :image_drive_link, :image_file_name)
                RETURNING id
            """),
            params,
        )
        return result.scalar()
    else:
        # SQLite fallback
        session.execute(
            text("""
                INSERT INTO comment_entries
                    (request_id, author_email, author_name, content, entry_type,
                     image_drive_link, image_file_name)
                VALUES
                    (:request_id, :author_email, :author_name, :content, :entry_type,
                     :image_drive_link, :image_file_name)
            """),
            params,
        )
        row = session.execute(
            text("SELECT id FROM comment_entries WHERE rowid = last_insert_rowid()")
        ).fetchone()
        return row[0] if row else None


def get_comment_entries(session: Session, request_id: int) -> list[dict]:
    """Return all comment entries for a request, newest first."""
    rows = session.execute(
        text("""
            SELECT id, author_email, author_name, content, entry_type,
                   image_drive_link, image_file_name, created_at
            FROM comment_entries
            WHERE request_id = :rid
            ORDER BY created_at DESC
        """),
        {"rid": request_id},
    ).fetchall()

    return [
        {
            "id": r.id,
            "author_email": r.author_email,
            "author_name": r.author_name,
            "content": r.content,
            "entry_type": r.entry_type,
            "image_drive_link": r.image_drive_link,
            "image_file_name": r.image_file_name,
            "created_at": r.created_at,
        }
        for r in rows
    ]


# ==========================
# NOTIFICATIONS
# ==========================

def insert_notification(
    session: Session,
    user_email: str,
    request_id: int,
    message: str,
) -> None:
    """Create an in-app notification for a user."""
    session.execute(
        text("""
            INSERT INTO notifications (user_email, request_id, message)
            VALUES (:user_email, :request_id, :message)
        """),
        {"user_email": user_email, "request_id": request_id, "message": message},
    )


def get_unread_notifications(session: Session, user_email: str) -> list[dict]:
    """Return unread notifications for a user."""
    rows = session.execute(
        text("""
            SELECT n.id, n.request_id, n.message, n.created_at,
                   r.company_name
            FROM notifications n
            LEFT JOIN requests r ON r.id = n.request_id
            WHERE n.user_email = :email AND n.is_read = FALSE
            ORDER BY n.created_at DESC
        """),
        {"email": user_email},
    ).fetchall()

    return [
        {
            "id": r.id,
            "request_id": r.request_id,
            "message": r.message,
            "created_at": r.created_at,
            "company_name": r.company_name,
        }
        for r in rows
    ]


def mark_notifications_read(session: Session, user_email: str) -> None:
    """Mark all notifications as read for a user."""
    session.execute(
        text("UPDATE notifications SET is_read = TRUE WHERE user_email = :email"),
        {"email": user_email},
    )


# ==========================
# AUDIT TIMELINE
# ==========================

def get_audit_timeline(session: Session, request_id: int, limit: int = 50) -> list[dict]:
    """Return chronological audit entries for a request (newest first)."""
    # Use exact delimiter "Request #N: " (with space after colon) to avoid
    # matching Request #10 when searching for Request #1
    rows = session.execute(
        text("""
            SELECT timestamp, user_email, action, entity_type,
                   entity_id, old_value, new_value, details
            FROM audit_log
            WHERE entity_id = :rid
               OR details LIKE :pattern
            ORDER BY timestamp DESC
            LIMIT :limit
        """),
        {"rid": request_id, "pattern": f"Request #{request_id}: %", "limit": limit}
    ).fetchall()

    return [
        {
            "timestamp": r.timestamp,
            "user_email": r.user_email,
            "action": r.action,
            "entity_type": r.entity_type,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "details": r.details,
        }
        for r in rows
    ]


def get_last_status_change_time(session: Session, entity_type: str, entity_id: int) -> Optional[datetime]:
    """Return the timestamp of the last STATUS_CHANGE for an entity.

    Used for SLA tracking (C4) - how long an item has been in its current status.
    """
    row = session.execute(
        text("""
            SELECT timestamp
            FROM audit_log
            WHERE action = 'STATUS_CHANGE'
              AND entity_type = :entity_type
              AND entity_id = :entity_id
            ORDER BY timestamp DESC
            LIMIT 1
        """),
        {"entity_type": entity_type, "entity_id": entity_id},
    ).fetchone()
    return row.timestamp if row else None
