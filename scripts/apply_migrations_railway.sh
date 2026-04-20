#!/usr/bin/env bash
# Apply pending migrations to a Railway environment.
#
# Usage:
#   ./scripts/apply_migrations_railway.sh <environment>
#   ./scripts/apply_migrations_railway.sh dev
#   ./scripts/apply_migrations_railway.sh production
#
# Requirements (one-time):
#   - Railway CLI installed: npm install -g @railway/cli
#   - `railway login` done on your laptop
#   - `railway link` to the compliance project
#
# What it does:
#   1. Switches to the requested environment.
#   2. Runs migrations/run_migration.py inside Railway's context so
#      DATABASE_URL is sourced from the environment.
#   3. Applies migrations 005 and 006 in order.
#
# Idempotent: both migrations use guards (IF NOT EXISTS, ON CONFLICT).
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <environment-name>"
    echo "Example: $0 production"
    exit 2
fi

ENV_NAME="$1"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

_log() { printf '\033[1;34m[railway-migrate]\033[0m %s\n' "$*"; }
_err() { printf '\033[1;31m[railway-migrate]\033[0m %s\n' "$*" >&2; }

command -v railway >/dev/null 2>&1 || {
    _err "Railway CLI not installed. Run: npm install -g @railway/cli"
    exit 1
}

_log "Switching to environment: $ENV_NAME"
railway environment "$ENV_NAME"

_log "Applying migration 005 (email_notified_at column)"
railway run python migrations/run_migration.py migrations/005_email_notifications.sql

_log "Applying migration 006 (seed lbandera as compliance admin)"
railway run python migrations/run_migration.py migrations/006_seed_admin_lbandera.sql

_log "Done. Verifying users table contains lbandera:"
railway run python -c "
import os, sqlalchemy as sa
eng = sa.create_engine(os.environ['DATABASE_URL'])
with eng.connect() as c:
    rows = list(c.execute(sa.text(\"SELECT email, rol, activo FROM users WHERE email='lbandera@tradingsolutions.com'\")).all())
print('Post-migration users check:', rows)
"
