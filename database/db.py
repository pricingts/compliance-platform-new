# database/db.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

try:
    import streamlit as st
    DATABASE_URL = st.secrets["DATABASE_URL"]
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL no está definida. Revisa tus secretos o tu archivo .env")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)