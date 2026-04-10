# database/crud/clientes.py

from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional


def get_profile_id(session: Session, profile_name: str) -> Optional[int]:
    """Return the profile id for the given profile name, or None if not found."""
    return session.execute(
        text("SELECT id FROM profiles WHERE name = :name"),
        {"name": profile_name.lower()},
    ).scalar()


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
) -> int:
    """Insert a new client/provider request and return the new row id."""
    session.execute(
        text("""
            INSERT INTO requests (
                profile_id, commercial, company_name, trading, country,
                language, email, reminder_frequency, operation_type,
                commodity, customs_req, has_customs, has_port,
                has_shipping_line, user_email
            )
            VALUES (
                :profile_id, :commercial, :company_name, :trading, :country,
                :language, :email, :reminder_frequency, :operation_type,
                :commodity, :customs_req, :has_customs, :has_port,
                :has_shipping_line, :user_email
            )
        """),
        {
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
        },
    )
    session.commit()

    # Retrieve the last inserted row id (works for both PostgreSQL and SQLite)
    request_id = session.execute(
        text("SELECT id FROM requests WHERE rowid = last_insert_rowid()")
    ).scalar()

    # Fallback for PostgreSQL (which doesn't have last_insert_rowid)
    if request_id is None:
        request_id = session.execute(
            text(
                "SELECT id FROM requests WHERE profile_id = :pid "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"pid": profile_id},
        ).scalar()

    return request_id


def insert_customs_registration(
    session: Session, request_id: int, customs_list: list
) -> None:
    """Insert customs registration rows for a request."""
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
    session.commit()


def insert_port_registration(
    session: Session, request_id: int, ports_dict: dict
) -> None:
    """Insert port and terminal registration rows for a request.

    ports_dict example: {'Cartagena': ['Contecar', 'SPRC'], 'Buenaventura': ['TCBUEN']}
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
    session.commit()


def insert_shipping_line_registration(
    session: Session, request_id: int, lines_data: dict
) -> None:
    """Insert shipping line registration rows with details for a request."""
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
    session.commit()

