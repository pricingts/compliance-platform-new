"""Shared form patterns -- cached data wrappers and reusable UI components."""
from __future__ import annotations

import streamlit as st
from database.db import SessionLocal
from database.crud.documents import (
    get_all_company_names,
    get_profiles_list,
    get_all_statuses,
    get_profile_id_by_name,
)


@st.cache_data(ttl=60)
def cached_company_names() -> list[str]:
    """Return company names, cached for 60 seconds."""
    session = SessionLocal()
    try:
        return get_all_company_names(session)
    finally:
        session.close()


@st.cache_data(ttl=60)
def cached_profiles_list() -> list[str]:
    """Return profile names, cached for 60 seconds."""
    session = SessionLocal()
    try:
        return get_profiles_list(session)
    finally:
        session.close()


@st.cache_data(ttl=120)
def cached_statuses() -> dict[str, int]:
    """Return {status_name: status_id} dict, cached for 120 seconds."""
    session = SessionLocal()
    try:
        return get_all_statuses(session)
    finally:
        session.close()


def status_id_to_name_map() -> dict[int, str]:
    """Return {status_id: status_name} reversed map."""
    return {v: k for k, v in cached_statuses().items()}


def cached_profile_id(profile_name: str) -> int | None:
    """Return profile_id by name, using a fresh session."""
    session = SessionLocal()
    try:
        return get_profile_id_by_name(session, profile_name)
    finally:
        session.close()
