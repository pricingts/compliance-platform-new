"""Run migration 002 against the Railway PostgreSQL database."""
import os
import sqlalchemy
from sqlalchemy import text

from services.logging_config import get_logger

logger = get_logger(__name__)

# Prefer public URL for external access, fallback to internal
DATABASE_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set. Run via: railway run python migrations/run_migration.py")

engine = sqlalchemy.create_engine(DATABASE_URL)

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_email VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id INTEGER,
    old_value TEXT,
    new_value TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS comment_entries (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    author_email VARCHAR(255) NOT NULL,
    author_name VARCHAR(255),
    content TEXT NOT NULL,
    entry_type VARCHAR(50) DEFAULT 'comment',
    image_drive_link TEXT,
    image_file_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_comment_entries_request_id ON comment_entries(request_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_email ON notifications(user_email);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity_id ON audit_log(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
"""

with engine.connect() as conn:
    for statement in MIGRATION_SQL.strip().split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(text(statement))
    conn.commit()

logger.info("Migration 002 applied successfully!")

# Verify tables exist
with engine.connect() as conn:
    for table in ["comment_entries", "notifications"]:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        count = result.scalar()
        logger.info("  %s: %s rows", table, count)
