"""Health check endpoint for Railway deployment monitoring."""
from sqlalchemy import text
from services.logging_config import get_logger

logger = get_logger(__name__)


def _get_engine():
    """Lazy import to avoid module-level DB initialization."""
    from database.db import engine
    return engine


def check_db() -> bool:
    """Check if the database is reachable."""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def health_status() -> dict:
    """Return the overall health status."""
    db_ok = check_db()
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": db_ok,
    }
