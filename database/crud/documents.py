# database/crud/documents.py

from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from typing import Optional

# ==========================
# 🔹 EMPRESAS Y PERFILES
# ==========================

def get_all_company_names(session: Session):
    rows = session.execute(
        text("SELECT DISTINCT company_name FROM requests ORDER BY company_name ASC")
    ).fetchall()
    return [r[0] for r in rows if r[0]]

def get_profiles_list(session: Session):
    rows = session.execute(
        text("SELECT name FROM profiles ORDER BY name ASC")
    ).fetchall()
    return [r[0] for r in rows if r[0]]

def get_profile_id_by_name(session: Session, profile_name: str):
    return session.execute(
        text("SELECT id FROM profiles WHERE name = :n"),
        {"n": profile_name}
    ).scalar()

# ==========================
# 🔹 SOLICITUDES EXISTENTES
# ==========================

def get_requests_by_company_and_profile(session: Session, company_name: str, profile_id: int, limit: int = 20):
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

def get_required_document_types(session: Session, profile_id: int):
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

def get_uploaded_documents_map(session: Session, request_id: int):
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


def upsert_uploaded_document(session: Session, request_id: int, document_type_id: int,
                             file_name: str, drive_link: str, uploaded_by: str,
                            razon_social: Optional[str] = None,
                            fecha_creacion: Optional[datetime] = None):
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


def get_request_meta(session: Session, request_id: int):
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

def update_request_meta(session: Session, request_id: int, notifications: str, comments: str):
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

def get_all_statuses(session):
    rows = session.execute(text("SELECT id, status FROM status ORDER BY id")).fetchall()
    return {r[1]: r[0] for r in rows}


def get_shipping_lines_status(session, request_id):
    return session.execute(text("""
        SELECT id, line_name, status_id
        FROM shipping_line_registration
        WHERE request_id = :req
    """), {"req": request_id}).fetchall()

def get_ports_status(session, request_id):
    return session.execute(text("""
        SELECT id, port_name, terminal_name, status_id
        FROM port_registration
        WHERE request_id = :req
    """), {"req": request_id}).fetchall()

def get_customs_status(session, request_id):
    return session.execute(text("""
        SELECT id, customs_name, status_id
        FROM customs_registration
        WHERE request_id = :req
    """), {"req": request_id}).fetchall()


def update_status(session, table_name: str, record_id: int, status_id: int):
    session.execute(
        text(f"UPDATE {table_name} SET status_id = :st WHERE id = :rid"),
        {"st": status_id, "rid": record_id}
    )

def upsert_status(session, table_name: str, request_id: int, entity_name: str, status_id: int, terminal_name: Optional[str] = None):
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

    if terminal_field:
        if terminal_field:
            terminal_clean = terminal_name.strip() if terminal_name else None
            params["terminal_name"] = terminal_clean

            existing = session.execute(
                text(f"""
                    SELECT id FROM {table_name}
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
                session.execute(
                    text(f"UPDATE {table_name} SET status_id = :status_id WHERE id = :id"),
                    {"status_id": status_id, "id": existing[0]},
                )
            else:
                session.execute(
                    text(f"""
                        INSERT INTO {table_name} (request_id, {name_field}, {terminal_field}, status_id)
                        VALUES (:request_id, :name, :terminal_name, :status_id)
                    """),
                    params
                )

        if existing:
            session.execute(
                text(f"UPDATE {table_name} SET status_id = :status_id WHERE id = :id"),
                {"status_id": status_id, "id": existing[0]},
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
                SELECT id FROM {table_name}
                WHERE request_id = :request_id
                AND {name_field} = :name
            """),
            params
        ).fetchone()

        if existing:
            session.execute(
                text(f"UPDATE {table_name} SET status_id = :status_id WHERE id = :id"),
                {"status_id": status_id, "id": existing[0]},
            )
        else:
            session.execute(
                text(f"""
                    INSERT INTO {table_name} (request_id, {name_field}, status_id)
                    VALUES (:request_id, :name, :status_id)
                """),
                params
            )

def get_internal_status(session, request_id):
    row = session.execute(
        text("SELECT status_id FROM internal_registration WHERE request_id = :rid"),
        {"rid": request_id}
    ).fetchone()
    return row[0] if row else None

def get_request_creation_date(session, request_id: int):
    row = session.execute(
        text("SELECT fecha_creacion FROM registration WHERE request_id = :rid LIMIT 1"),
        {"rid": request_id}
    ).fetchone()
    return row[0] if row else None

def get_comments_by_request(session, request_id: int):
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
    session,
    request_id: int,
    uploaded_by: str,
    razon_social: Optional[str] = None,
    fecha_creacion: Optional[datetime] = None
):
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

def get_razon_social_by_request(session, request_id: int):
    result = session.execute(
        text("""
            SELECT razon_social
            FROM registration
            WHERE request_id = :rid
            LIMIT 1
        """),
        {"rid": request_id}
    ).fetchone()

    return result[0] if result and result[0] else None

def get_requests_for_progress(session, only_for_email: str | None = None):

    sql = text("""
        SELECT
            id,
            company_name,
            profile_id,
            created_at,
            email
        FROM requests
        WHERE (:email IS NULL OR LOWER(email) = LOWER(:email))
        ORDER BY created_at DESC
    """)
    rows = session.execute(sql, {"email": only_for_email}).fetchall()
    return [
        {
            "id": r.id,
            "company_name": r.company_name,
            "profile_id": r.profile_id,
            "created_at": r.created_at,
            "email": r.email,
        }
        for r in rows
    ]
