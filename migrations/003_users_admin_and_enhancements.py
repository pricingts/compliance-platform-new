"""Run migration 003 against the Railway PostgreSQL database.

Adds:
- users table (email PK, rol, activo)
- inside_sales_comerciales many-to-many link table
- request_attachments table
- reminder_schedule table
- New columns on requests: submitted_by_email, notes, case_id, reminder_max_months
- Backfill case_id for historical rows

After this migration, also run seed_super_admin.sql to create the sole
hardcoded admin (jsanchez@tradingsolutions.com). Everything else is managed
via the admin panel in the UI.

Usage:
    railway run python migrations/003_users_admin_and_enhancements.py
"""
from __future__ import annotations

import os
from pathlib import Path

import sqlalchemy
from sqlalchemy import text

from services.logging_config import get_logger

logger = get_logger(__name__)

MIGRATION_SQL_PATH = Path(__file__).parent / "003_users_admin_and_enhancements.sql"
SEED_SQL_PATH = Path(__file__).parent / "seed_super_admin.sql"


def _get_database_url() -> str:
    """Prefer public URL for external access, fallback to internal."""
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Run via: railway run python migrations/003_users_admin_and_enhancements.py"
        )
    return url


def _strip_sql_comments(sql: str) -> str:
    """Remove full-line `--` comments and blank lines.

    We can't strip on `startswith("--")` per-statement because real DDL
    statements often have a comment header right above them (and after a
    naive `split(';')` they end up in the same chunk, prefixed by `--`).
    """
    out_lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue  # full-line comment
        out_lines.append(line)
    return "\n".join(out_lines)


def _execute_sql_file(engine, sql_path: Path) -> None:
    """Execute a SQL file, splitting on semicolons.

    Note: naive split on ';' — the migration files are hand-written and don't
    contain semicolons inside strings or function bodies.
    """
    raw_sql = sql_path.read_text()
    cleaned = _strip_sql_comments(raw_sql)
    with engine.connect() as conn:
        for statement in cleaned.split(";"):
            statement = statement.strip()
            if not statement:
                continue
            conn.execute(text(statement))
        conn.commit()


def run() -> None:
    database_url = _get_database_url()
    engine = sqlalchemy.create_engine(database_url)

    logger.info("Applying migration 003 from %s...", MIGRATION_SQL_PATH.name)
    _execute_sql_file(engine, MIGRATION_SQL_PATH)
    logger.info("Migration 003 applied.")

    if SEED_SQL_PATH.exists():
        logger.info("Applying seed %s...", SEED_SQL_PATH.name)
        _execute_sql_file(engine, SEED_SQL_PATH)
        logger.info("Seed applied.")
    else:
        logger.warning(
            "seed file %s not found — skipping super-admin seed.", SEED_SQL_PATH.name
        )

    # Verify new tables/columns exist
    with engine.connect() as conn:
        for table in ["users", "inside_sales_comerciales", "request_attachments", "reminder_schedule"]:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            logger.info("  %s: %s rows", table, count)

        new_cols = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'requests'
               AND column_name IN ('submitted_by_email','notes','case_id','reminder_max_months')
             ORDER BY column_name
        """)).fetchall()
        logger.info("  requests new columns: %s", [r[0] for r in new_cols])

        null_case_ids = conn.execute(text(
            "SELECT COUNT(*) FROM requests WHERE case_id IS NULL"
        )).scalar()
        logger.info("  requests with NULL case_id (should be 0): %s", null_case_ids)


if __name__ == "__main__":
    run()
