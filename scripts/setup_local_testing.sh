#!/usr/bin/env bash
# Set up a local testing environment for the compliance platform.
#
# What it does (in order):
#   1. Verifies prerequisites (docker, docker-compose, python3).
#   2. Brings up the Postgres container via docker-compose (init_db.sql runs automatically).
#   3. Waits until Postgres is ready on localhost:5433.
#   4. Applies any pending migrations (005, 006, and future numbered files).
#   5. Installs Python test dependencies.
#   6. Runs the full test suite against the Docker Postgres.
#   7. Prints a summary and the URL to launch the Streamlit app if desired.
#
# Usage:
#   ./scripts/setup_local_testing.sh             # full setup + tests
#   ./scripts/setup_local_testing.sh --no-tests  # only bring up infra, skip pytest
#   ./scripts/setup_local_testing.sh --down      # tear everything down
#
# Requirements on your machine (one-time):
#   - Docker Desktop running
#   - Python 3.11+ with pip
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

LOCAL_DB_URL="postgresql://admin:admin@localhost:5433/compliance_new_db"

_log() { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
_err() { printf '\033[1;31m[setup]\033[0m %s\n' "$*" >&2; }

_require() {
    command -v "$1" >/dev/null 2>&1 || { _err "missing dependency: $1"; exit 1; }
}

_wait_for_db() {
    local attempts=30
    while [ $attempts -gt 0 ]; do
        if docker compose exec -T db pg_isready -U admin -d compliance_new_db >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempts=$((attempts - 1))
    done
    _err "Postgres did not become ready in time"
    return 1
}

cmd_up() {
    _log "Prerequisites check"
    _require docker
    _require python3

    _log "Starting Docker Compose (Postgres on :5433)"
    docker compose up -d db

    _log "Waiting for Postgres to accept connections"
    _wait_for_db

    _log "Applying outstanding SQL migrations (005, 006, …)"
    DATABASE_URL="$LOCAL_DB_URL" python3 migrations/run_migration.py \
        migrations/005_email_notifications.sql \
        migrations/006_seed_admin_lbandera.sql

    _log "Applying seed_super_admin.sql (idempotent)"
    DATABASE_URL="$LOCAL_DB_URL" python3 migrations/run_migration.py \
        migrations/seed_super_admin.sql

    _log "Installing Python deps (including dev)"
    pip install -q -r requirements.txt -r requirements-dev.txt

    _log "Confirming lbandera is seeded"
    docker compose exec -T db psql -U admin -d compliance_new_db \
        -c "SELECT email, rol, activo FROM users WHERE email IN ('lbandera@tradingsolutions.com','jsanchez@tradingsolutions.com') ORDER BY email;"

    _log "Infrastructure ready."
    _log "  DATABASE_URL for local dev: $LOCAL_DB_URL"
    _log "  Streamlit app would run at: http://localhost:8501"
}

cmd_tests() {
    _log "Running pytest against the Docker Postgres"
    DATABASE_URL="$LOCAL_DB_URL" python3 -m pytest tests/unit tests/integration -q --tb=short
}

cmd_down() {
    _log "Tearing down docker-compose stack and volumes"
    docker compose down -v
}

mode="${1:-up-and-tests}"
case "$mode" in
    --no-tests)
        cmd_up
        ;;
    --down)
        cmd_down
        ;;
    up-and-tests | "")
        cmd_up
        cmd_tests
        ;;
    *)
        _err "Unknown option: $mode"
        echo "Usage: $0 [--no-tests | --down]"
        exit 2
        ;;
esac

_log "Done."
