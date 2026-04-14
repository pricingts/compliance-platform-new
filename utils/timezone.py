"""Centralized timezone handling for the compliance platform."""
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

CO_TZ = ZoneInfo("America/Bogota")

def get_colombia_tz() -> ZoneInfo:
    """Return the Colombia timezone."""
    return CO_TZ

def utc_now() -> datetime:
    """Return current datetime in UTC as a naive datetime.

    Drop-in replacement for the deprecated ``datetime.utcnow()``. We strip the
    tzinfo because every TIMESTAMP column in the schema is naive (TIMESTAMP
    WITHOUT TIME ZONE), and mixing aware/naive datetimes raises TypeError.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

def now_colombia() -> datetime:
    """Return current datetime in Colombia timezone."""
    return datetime.now(timezone.utc).astimezone(CO_TZ)

def to_colombia_tz(dt: datetime = None) -> datetime:
    """Convert a datetime to Colombia timezone. If naive, assumes UTC."""
    if dt is None:
        return now_colombia()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CO_TZ)
