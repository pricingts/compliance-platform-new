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

def insert_client_request(profile_id, company_name=None, email=None, trading=None, location=None, language=None, reminder_frequency=None,
                            colaborador_nombre=None,colaborador_cedula=None, requested_by: str = None,  requested_by_type: str = None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO clients_requests (
            profile_id, company_name, email, trading, location, language, reminder_frequency, colaborador_nombre, colaborador_cedula, requested_by, requested_by_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (
        profile_id, company_name, email, trading, location, language, reminder_frequency, colaborador_nombre, colaborador_cedula, requested_by, requested_by_type))

    request_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return request_id

