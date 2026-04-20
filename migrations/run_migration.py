"""Generic migration runner for the compliance platform.

Usage (from the project root):

    # Against Railway (environment-switched via `railway environment <name>`):
    railway run python migrations/run_migration.py migrations/005_email_notifications.sql
    railway run python migrations/run_migration.py migrations/006_seed_admin_lbandera.sql

    # Against a local .env DATABASE_URL:
    python migrations/run_migration.py migrations/005_email_notifications.sql

    # Apply a batch of migrations in order (globs allowed):
    python migrations/run_migration.py migrations/00*.sql

The runner:
- Reads DATABASE_URL (preferring DATABASE_PUBLIC_URL when present so you can
  connect to Railway from your laptop).
- Applies each SQL file inside a single transaction (commit on success,
  rollback on error, then continue to the next file after logging).
- Splits on semicolons that terminate statements. Handles embedded semicolons
  inside dollar-quoted blocks (``$$ ... $$``) so PL/pgSQL DO-blocks stay intact.
- Idempotent: the shipped migrations use ``IF NOT EXISTS`` / ``ON CONFLICT``
  guards, so reruns are safe.

Exit codes:
    0 = all files applied successfully
    1 = at least one file failed (error logged, transaction rolled back)
    2 = misuse (no arguments, bad path, missing DATABASE_URL)
"""
from __future__ import annotations

import os
import sys
from glob import glob
from pathlib import Path

# Ensure the project root is importable when this file is run directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import sqlalchemy  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.logging_config import get_logger  # noqa: E402

logger = get_logger(__name__)


def _load_database_url() -> str:
    """Return the DATABASE_URL to connect to, or exit(2) if not available."""
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not url:
        # Try .env as a last resort (local dev).
        try:
            from dotenv import load_dotenv

            load_dotenv()
            url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
        except ImportError:
            pass
    if not url:
        logger.error(
            "DATABASE_URL not set. Run via: railway run python migrations/run_migration.py "
            "<path.sql> OR export DATABASE_URL=... in your shell."
        )
        sys.exit(2)
    return url


def _split_statements(sql: str) -> list[str]:
    """Split a SQL blob on statement-terminating semicolons.

    Respects:
    - ``$$ ... $$`` dollar-quoted blocks (common in PL/pgSQL DO-blocks).
    - ``'...'`` single-quoted string literals.
    - ``--`` single-line comments (to end of line).
    - ``/* ... */`` block comments.

    Does not attempt to handle nested block comments (Postgres supports them;
    the shipped migrations don't use them).
    """
    statements: list[str] = []
    buffer: list[str] = []
    in_dollar = False
    in_single_quote = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        # End-of-line comment terminator.
        if in_line_comment:
            buffer.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # Block comment terminator.
        if in_block_comment:
            buffer.append(ch)
            if ch == "*" and nxt == "/":
                buffer.append(nxt)
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        # Inside single-quoted string: only toggle on closing quote.
        if in_single_quote:
            buffer.append(ch)
            if ch == "'":
                # SQL escapes '' as a literal quote. Do not close yet.
                if nxt == "'":
                    buffer.append(nxt)
                    i += 2
                    continue
                in_single_quote = False
            i += 1
            continue

        # Inside dollar-quoted block.
        if in_dollar:
            if sql[i : i + 2] == "$$":
                in_dollar = False
                buffer.append("$$")
                i += 2
                continue
            buffer.append(ch)
            i += 1
            continue

        # Not in any quote/comment: check for openers.
        if ch == "-" and nxt == "-":
            in_line_comment = True
            buffer.append(ch)
            buffer.append(nxt)
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            buffer.append(ch)
            buffer.append(nxt)
            i += 2
            continue
        if sql[i : i + 2] == "$$":
            in_dollar = True
            buffer.append("$$")
            i += 2
            continue
        if ch == "'":
            in_single_quote = True
            buffer.append(ch)
            i += 1
            continue
        if ch == ";":
            stmt = "".join(buffer).strip()
            if stmt:
                statements.append(stmt)
            buffer = []
            i += 1
            continue

        buffer.append(ch)
        i += 1

    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def apply_file(engine, path: Path) -> None:
    """Apply one SQL file as a single transaction."""
    logger.info("Applying %s", path.name)
    sql_text = path.read_text(encoding="utf-8")
    statements = _split_statements(sql_text)
    logger.info("  %d statement(s) in file", len(statements))

    with engine.begin() as conn:  # commit on success, rollback on exc
        for i, stmt in enumerate(statements, 1):
            first_line = stmt.splitlines()[0] if stmt.strip() else ""
            preview = first_line[:80]
            logger.info("  [%d/%d] %s...", i, len(statements), preview)
            conn.execute(text(stmt))

    logger.info("OK %s applied", path.name)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        logger.error(
            "Usage: python migrations/run_migration.py <file.sql> [file2.sql ...]"
        )
        return 2

    raw_targets: list[str] = []
    for pattern in argv[1:]:
        matched = glob(pattern)
        if matched:
            raw_targets.extend(sorted(matched))
        else:
            raw_targets.append(pattern)

    paths: list[Path] = []
    for t in raw_targets:
        p = Path(t)
        if not p.exists():
            logger.error("File not found: %s", t)
            return 2
        if p.suffix != ".sql":
            logger.error("Not a .sql file (skipping): %s", t)
            continue
        paths.append(p)

    if not paths:
        logger.error("No .sql files to apply.")
        return 2

    url = _load_database_url()
    safe_url = url.split("@", 1)[-1] if "@" in url else url
    logger.info("Connecting to %s", safe_url)
    engine = sqlalchemy.create_engine(url)

    failures: list[str] = []
    for path in paths:
        try:
            apply_file(engine, path)
        except Exception:
            logger.exception("FAILED applying %s", path.name)
            failures.append(path.name)

    if failures:
        logger.error("Some migrations failed: %s", ", ".join(failures))
        return 1
    logger.info("All migrations applied successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
