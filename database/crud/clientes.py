import psycopg2
import os

def get_connection():
    # 1. Intenta leer DATABASE_URL de Streamlit Cloud (secrets) o de las env vars locales
    try:
        import streamlit as st
        url = st.secrets["DATABASE_URL"]
    except Exception:
        url = os.getenv("DATABASE_URL")

    if not url:
        raise ValueError("DATABASE_URL no está definido en secrets ni en el entorno.")

    return psycopg2.connect(dsn=url)

def get_profile_id(profile_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM profiles WHERE name = %s", (profile_name.lower(),))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else None

def insert_client_request(
    profile_id: int,
    company_name: str = None,
    email: str = None,
    trading: str = None,
    location: str = None,          # se mapeará a country
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
    user_email: str = None
):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO requests (
            profile_id,
            commercial,
            company_name,
            trading,
            country,
            language,
            email,
            reminder_frequency,
            operation_type,
            commodity,
            customs_req,
            has_customs,
            has_port,
            has_shipping_line,
            user_email
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (
        profile_id,
        requested_by,                # se guarda como 'commercial' si es cliente
        company_name,
        trading,
        location,                    # mapeado a 'country'
        language,
        email,
        reminder_frequency,
        operation_type,
        commodity,
        customs_req,
        has_customs,
        has_port,
        has_shipping_line,
        user_email
    ))

    request_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return request_id

def insert_customs_registration(request_id: int, customs_list: list):
    """Guarda múltiples aduanas asociadas a una solicitud."""
    if not customs_list:
        return
    conn = get_connection()
    cur = conn.cursor()
    for customs_name in customs_list:
        cur.execute("""
            INSERT INTO customs_registration (request_id, customs_name)
            VALUES (%s, %s);
        """, (request_id, customs_name))
    conn.commit()
    cur.close()
    conn.close()

def insert_port_registration(request_id: int, ports_dict: dict):
    """Guarda puertos y terminales asociadas a una solicitud.
        ports_dict ejemplo: {'Cartagena': ['Contecar', 'SPRC'], 'Buenaventura': ['TCBUEN']}"""
    if not ports_dict:
        return
    conn = get_connection()
    cur = conn.cursor()
    for port_name, terminals in ports_dict.items():
        if not terminals:
            cur.execute("""
                INSERT INTO port_registration (request_id, port_name)
                VALUES (%s, %s);
            """, (request_id, port_name))
        else:
            for terminal in terminals:
                cur.execute("""
                    INSERT INTO port_registration (request_id, port_name, terminal_name)
                    VALUES (%s, %s, %s);
                """, (request_id, port_name, terminal))
    conn.commit()
    cur.close()
    conn.close()


def insert_shipping_line_registration(request_id: int, lines_data: dict):
    """Guarda las líneas navieras con su información."""
    if not lines_data:
        return
    conn = get_connection()
    cur = conn.cursor()
    for line_name, line_info in lines_data.items():
        cur.execute("""
            INSERT INTO shipping_line_registration
            (request_id, line_name, pol, pod, product, container_type, shipper_bl)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (
            request_id,
            line_name,
            line_info.get("POL"),
            line_info.get("POD"),
            line_info.get("Producto"),
            line_info.get("Tipo de Contenedor"),
            line_info.get("Shipper en BL")
        ))
    conn.commit()
    cur.close()
    conn.close()

