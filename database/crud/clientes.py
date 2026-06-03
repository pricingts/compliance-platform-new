# database/crud/clientes.py

from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional


def format_case_id(request_id: int) -> str:
    """Format a numeric request id into the human-friendly case id format.

    Examples:
        1     -> 'C0001'
        42    -> 'C0042'
        9999  -> 'C9999'
        10000 -> 'C10000'   # wider than 4 digits when id exceeds 9999

    The 4-digit padding is the canonical format; ids beyond 9999 overflow
    gracefully by using as many digits as needed.
    """
    return f"C{request_id:04d}"


def get_profile_id(session: Session, profile_name: str) -> Optional[int]:
    """Return the profile id for the given profile name, or None if not found."""
    return session.execute(
        text("SELECT id FROM profiles WHERE name = :name"),
        {"name": profile_name.lower()},
    ).scalar()


def get_case_id(session: Session, request_id: int) -> Optional[str]:
    """Return the case_id (C0001...) for a request, or None if not found."""
    return session.execute(
        text("SELECT case_id FROM requests WHERE id = :id"),
        {"id": request_id},
    ).scalar()


def get_request_by_case_id(session: Session, case_id: str) -> Optional[dict]:
    """Look up a request by its human-friendly case_id. Case-insensitive."""
    if not case_id:
        return None
    row = session.execute(
        text("""
            SELECT id, case_id, company_name, commercial, profile_id, user_email,
                   submitted_by_email, notes, created_at
              FROM requests
             WHERE UPPER(case_id) = UPPER(:cid)
        """),
        {"cid": case_id.strip()},
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "case_id": row[1],
        "company_name": row[2],
        "commercial": row[3],
        "profile_id": row[4],
        "user_email": row[5],
        "submitted_by_email": row[6],
        "notes": row[7],
        "created_at": row[8],
    }


def insert_client_request(
    session: Session,
    profile_id: int,
    company_name: str = None,
    email: str = None,
    trading: str = None,
    location: str = None,
    language: str = None,
    reminder_frequency: str = None,
    operation_type: str = None,
    commodity: str = None,
    customs_req: str = None,
    has_customs: bool = False,
    has_port: bool = False,
    has_shipping_line: bool = False,
    requested_by: str = None,
    requested_by_type: str = None,
    user_email: str = None,
    submitted_by_email: Optional[str] = None,
    notes: Optional[str] = None,
    reminder_max_months: Optional[int] = None,
    commit: bool = True,
) -> int:
    """Insert a new client/provider request and return the new row id.

    Uses INSERT ... RETURNING on PostgreSQL for race-condition-safe ID
    retrieval. Falls back to last_insert_rowid() on SQLite (test env).

    New params (migration 003):
    - submitted_by_email: set when an Inside Sales creates on behalf of a comercial
    - notes: free-text for compliance
    - reminder_max_months: upper bound (1/2/3) on reminder duration

    Set ``commit=False`` to let the caller own the transaction boundary so the
    parent row and its child registrations commit (or roll back) atomically.
    """
    params = {
        "profile_id": profile_id,
        "commercial": requested_by,
        "company_name": company_name,
        "trading": trading,
        "country": location,
        "language": language,
        "email": email,
        "reminder_frequency": reminder_frequency,
        "operation_type": operation_type,
        "commodity": commodity,
        "customs_req": customs_req,
        "has_customs": has_customs,
        "has_port": has_port,
        "has_shipping_line": has_shipping_line,
        "user_email": user_email,
        "submitted_by_email": submitted_by_email,
        "notes": notes,
        "reminder_max_months": reminder_max_months,
    }

    dialect = session.bind.dialect.name if session.bind else "unknown"

    if dialect == "postgresql":
        result = session.execute(
            text("""
                INSERT INTO requests (
                    profile_id, commercial, company_name, trading, country,
                    language, email, reminder_frequency, operation_type,
                    commodity, customs_req, has_customs, has_port,
                    has_shipping_line, user_email,
                    submitted_by_email, notes, reminder_max_months
                )
                VALUES (
                    :profile_id, :commercial, :company_name, :trading, :country,
                    :language, :email, :reminder_frequency, :operation_type,
                    :commodity, :customs_req, :has_customs, :has_port,
                    :has_shipping_line, :user_email,
                    :submitted_by_email, :notes, :reminder_max_months
                )
                RETURNING id
            """),
            params,
        )
        request_id = result.scalar()
    else:
        # SQLite path (used in tests)
        session.execute(
            text("""
                INSERT INTO requests (
                    profile_id, commercial, company_name, trading, country,
                    language, email, reminder_frequency, operation_type,
                    commodity, customs_req, has_customs, has_port,
                    has_shipping_line, user_email,
                    submitted_by_email, notes, reminder_max_months
                )
                VALUES (
                    :profile_id, :commercial, :company_name, :trading, :country,
                    :language, :email, :reminder_frequency, :operation_type,
                    :commodity, :customs_req, :has_customs, :has_port,
                    :has_shipping_line, :user_email,
                    :submitted_by_email, :notes, :reminder_max_months
                )
            """),
            params,
        )
        request_id = session.execute(
            text("SELECT id FROM requests WHERE rowid = last_insert_rowid()")
        ).scalar()

    # Generate and persist case_id (format: C0001). Runs on both dialects —
    # a SQL trigger is avoided to keep Postgres and SQLite consistent.
    case_id = format_case_id(request_id)
    session.execute(
        text("UPDATE requests SET case_id = :cid WHERE id = :rid"),
        {"cid": case_id, "rid": request_id},
    )

    if commit:
        session.commit()
    return request_id


def insert_customs_registration(
    session: Session, request_id: int, customs_list: list, commit: bool = True
) -> None:
    """Insert customs registration rows for a request.

    ``commit=False`` lets the caller keep the parent request and these child
    rows in one atomic transaction.
    """
    if not customs_list:
        return
    for customs_name in customs_list:
        session.execute(
            text(
                "INSERT INTO customs_registration (request_id, customs_name) "
                "VALUES (:request_id, :customs_name)"
            ),
            {"request_id": request_id, "customs_name": customs_name},
        )
    if commit:
        session.commit()


def insert_port_registration(
    session: Session, request_id: int, ports_dict: dict, commit: bool = True
) -> None:
    """Insert port and terminal registration rows for a request.

    ports_dict example: {'Cartagena': ['Contecar', 'SPRC'], 'Buenaventura': ['TCBUEN']}

    ``commit=False`` lets the caller keep the parent request and these child
    rows in one atomic transaction.
    """
    if not ports_dict:
        return
    for port_name, terminals in ports_dict.items():
        if not terminals:
            session.execute(
                text(
                    "INSERT INTO port_registration (request_id, port_name) "
                    "VALUES (:request_id, :port_name)"
                ),
                {"request_id": request_id, "port_name": port_name},
            )
        else:
            for terminal in terminals:
                session.execute(
                    text(
                        "INSERT INTO port_registration "
                        "(request_id, port_name, terminal_name) "
                        "VALUES (:request_id, :port_name, :terminal_name)"
                    ),
                    {
                        "request_id": request_id,
                        "port_name": port_name,
                        "terminal_name": terminal,
                    },
                )
    if commit:
        session.commit()


def insert_shipping_line_registration(
    session: Session, request_id: int, lines_data: dict, commit: bool = True
) -> None:
    """Insert shipping line registration rows with details for a request.

    ``commit=False`` lets the caller keep the parent request and these child
    rows in one atomic transaction.
    """
    if not lines_data:
        return
    for line_name, line_info in lines_data.items():
        session.execute(
            text(
                "INSERT INTO shipping_line_registration "
                "(request_id, line_name, pol, pod, product, container_type, shipper_bl) "
                "VALUES (:request_id, :line_name, :pol, :pod, :product, "
                ":container_type, :shipper_bl)"
            ),
            {
                "request_id": request_id,
                "line_name": line_name,
                "pol": line_info.get("POL"),
                "pod": line_info.get("POD"),
                "product": line_info.get("Producto"),
                "container_type": line_info.get("Tipo de Contenedor"),
                "shipper_bl": line_info.get("Shipper en BL"),
            },
        )
    if commit:
        session.commit()

