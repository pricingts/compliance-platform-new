"""SQLite-adapted version of migration 003 for LOCAL development only.

The production migration (003_users_admin_and_enhancements.py) uses Postgres
syntax (SERIAL, LPAD, `||` concat, partial indexes, CHECK constraints) that
SQLite does not fully support.

This script applies the equivalent schema to the local SQLite DB so you can
test the UI end-to-end without needing Railway credentials. Run it from the
project root:

    python migrations/003_sqlite_local.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "local_dev.db"
SUPER_ADMIN_EMAIL = "jsanchez@tradingsolutions.com"


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        email VARCHAR(255) PRIMARY KEY,
        nombre_display VARCHAR(255) NOT NULL,
        rol VARCHAR(20) NOT NULL,
        activo BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(255)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inside_sales_comerciales (
        inside_sales_email VARCHAR(255) NOT NULL REFERENCES users(email) ON DELETE CASCADE,
        comercial_email    VARCHAR(255) NOT NULL REFERENCES users(email) ON DELETE CASCADE,
        assigned_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        assigned_by        VARCHAR(255),
        PRIMARY KEY (inside_sales_email, comercial_email)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS request_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
        file_name VARCHAR(255) NOT NULL,
        drive_link TEXT NOT NULL,
        uploaded_by VARCHAR(255) NOT NULL,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reminder_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
        next_reminder_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT 1,
        frequency_days INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

NEW_REQUEST_COLUMNS = [
    ("submitted_by_email", "VARCHAR(255)"),
    ("notes", "TEXT"),
    ("case_id", "VARCHAR(10)"),
    ("reminder_max_months", "INTEGER"),
]


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} does not exist — run the app once or init the DB first.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    print(f"Applying migration 003 (SQLite) to {DB_PATH}…")

    # 1. New tables
    for sql in SCHEMA_STATEMENTS:
        cur.execute(sql)
    conn.commit()
    print("  ✓ new tables created")

    # 2. New columns on requests
    for col_name, col_type in NEW_REQUEST_COLUMNS:
        if not _column_exists(conn, "requests", col_name):
            cur.execute(f"ALTER TABLE requests ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ requests.{col_name} added")
        else:
            print(f"  · requests.{col_name} already present")
    conn.commit()

    # 3. Backfill case_id for existing rows
    cur.execute("""
        UPDATE requests
           SET case_id = 'C' || substr('0000' || id, -4)
         WHERE case_id IS NULL
    """)
    conn.commit()
    print(f"  ✓ case_id backfilled for {cur.rowcount} rows")

    # 4. Unique index for case_id (partial; SQLite supports this since 3.8)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_case_id_unique
                  ON requests(case_id) WHERE case_id IS NOT NULL
    """)
    conn.commit()
    print("  ✓ unique index on case_id ensured")

    # 5. Seed super-admin
    cur.execute(
        """
        INSERT INTO users (email, nombre_display, rol, activo, created_by)
        VALUES (?, 'Juan Sanchez', 'compliance', 1, 'seed')
        ON CONFLICT(email) DO UPDATE SET
            nombre_display = excluded.nombre_display,
            rol = excluded.rol,
            activo = excluded.activo
        """,
        (SUPER_ADMIN_EMAIL,),
    )
    conn.commit()
    print(f"  ✓ super-admin seeded: {SUPER_ADMIN_EMAIL}")

    # Verify
    row = cur.execute(
        "SELECT email, rol, activo FROM users WHERE email=?", (SUPER_ADMIN_EMAIL,)
    ).fetchone()
    print(f"\nVerification: users row = {row}")

    counts = {}
    for t in ("users", "inside_sales_comerciales", "request_attachments", "reminder_schedule"):
        counts[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"Table counts: {counts}")

    null_case_ids = cur.execute(
        "SELECT COUNT(*) FROM requests WHERE case_id IS NULL"
    ).fetchone()[0]
    print(f"Requests with NULL case_id: {null_case_ids}")

    conn.close()
    print("\nMigration 003 (SQLite) complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
