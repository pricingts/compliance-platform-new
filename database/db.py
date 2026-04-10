# database/db.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _get_database_url() -> str:
    """Resolve DATABASE_URL from Streamlit secrets or environment variables."""
    try:
        import streamlit as st
        return st.secrets["DATABASE_URL"]
    except Exception:
        from dotenv import load_dotenv
        load_dotenv()

    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL no esta definida. Revisa tus secretos o tu archivo .env")
    return url


DATABASE_URL = _get_database_url()

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
