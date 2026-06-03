# Deployment Guide

## Railway Deployment

The platform deploys to [Railway](https://railway.app/) using Docker. Configuration is defined in `railway.toml`.

### Prerequisites

- Railway CLI installed (`npm install -g @railway/cli`)
- Railway account with a project created
- PostgreSQL plugin added to the Railway project

### Deployment Steps

1. **Link your project**:
   ```bash
   railway login
   railway link
   ```

2. **Set environment variables** (see Required Variables below):
   ```bash
   railway variables set DATABASE_URL="postgresql://..."
   railway variables set ENV=production
   ```

3. **Deploy**:
   ```bash
   railway up
   ```

   Railway will build the Docker image and deploy it automatically.

4. **Generate a public domain**:
   ```bash
   railway domain
   ```

### Railway Configuration

The `railway.toml` file configures the deployment:

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true"
healthcheckPath = "/"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

Key settings:
- **Builder**: Uses the project Dockerfile for consistent builds
- **Start command**: Runs Streamlit on the Railway-assigned `$PORT`
- **Health check**: Pings `/` with a 300-second timeout for startup
- **Restart policy**: Automatically restarts on failure (up to 3 retries)

## Required Environment Variables

### Core

| Variable | Example | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` | PostgreSQL connection string (provided by Railway PostgreSQL plugin) |
| `ENV` | `production` | Environment identifier |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

### Google API Credentials

For Google Drive and Sheets integration, configure service account credentials. On Railway, use Streamlit secrets or set the credentials as environment variables:

| Variable | Description |
|---|---|
| `GOOGLE_DRIVE_CREDENTIALS_PATH` | Path to Google Drive service account JSON |
| `GOOGLE_SHEETS_CREDENTIALS_PATH` | Path to Google Sheets service account JSON |

Alternatively, on Streamlit Cloud, configure these in `.streamlit/secrets.toml`.

### Admin Configuration

| Variable | Default | Description |
|---|---|---|
| `ADMIN_EMAILS` | (none) | Comma-separated list of admin email addresses |
| `ADMIN_USERNAMES` | `compliance,compliance1,...` | Comma-separated admin usernames |
| `ADMIN_DOMAINS` | `@tradingsolutions.com,@tradingsol.com` | Comma-separated email domains |

If `ADMIN_EMAILS` is set, it takes precedence. Otherwise, admin emails are computed as the cross-product of `ADMIN_USERNAMES` and `ADMIN_DOMAINS`.

## Database Migrations

The project uses Alembic for database migrations.

### Running Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Check current migration version
alembic current

# Generate a new migration after model changes
alembic revision --autogenerate -m "description of changes"

# Downgrade one step
alembic downgrade -1
```

### Initial Schema

For fresh deployments, initialize the full schema with `init_db.sql`, then apply
the seed migrations so there is at least one admin user to log in with:

```bash
# 1. Full schema (all tables, columns and indexes — kept in sync with migrations)
psql $DATABASE_URL < init_db.sql

# 2. Seeds (admin + comerciales). Idempotent (ON CONFLICT), safe to re-run.
python migrations/run_migration.py migrations/006_seed_admin_lbandera.sql
python migrations/run_migration.py migrations/009_seed_comerciales.sql
psql $DATABASE_URL < migrations/seed_super_admin.sql
```

`init_db.sql` is the complete, current schema — it already includes every table
and column added by migrations 002–010 (`users`, `inside_sales_comerciales`,
`request_attachments`, `reminder_schedule`, `email_threads`, the `requests`
columns `case_id`/`notes`/`submitted_by_email`/`reminder_max_months`/
`email_notified_at`, and `email` as `TEXT`). When you add a new migration, mirror
its DDL here so fresh deployments stay correct.

> Note: the `.py` migrations (e.g. `003_users_admin_and_enhancements.py`,
> `003_sqlite_local.py`) are NOT picked up by `run_migration.py`'s `*.sql` glob —
> run them directly with `python migrations/<file>.py` when applying migrations
> to an existing database.

## Health Check

The Dockerfile includes a health check that verifies the Streamlit server is responsive:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1
```

Railway also performs its own health check against the configured `healthcheckPath` (`/`).

### Health Check Behavior

- **Interval**: Checks every 30 seconds
- **Timeout**: Fails if no response within 10 seconds
- **Start period**: Allows 30 seconds for initial startup before checking
- **Retries**: Marks unhealthy after 3 consecutive failures

## Monitoring and Logging

### Structured Logging

The application uses structured logging configured in `services/logging_config.py`. Log level is controlled by the `LOG_LEVEL` environment variable.

```bash
# Set to DEBUG for verbose output during troubleshooting
railway variables set LOG_LEVEL=DEBUG
```

### Railway Dashboard

Monitor deployments from the Railway dashboard:

- **Deploy logs**: View build and runtime output
- **Metrics**: CPU, memory, and network usage
- **Crash detection**: Automatic restart on failure with `ON_FAILURE` policy

### Viewing Logs

```bash
# Stream live logs
railway logs

# View recent deployment logs
railway logs --deployment
```

## Docker

### Local Docker Build

```bash
# Build the image
docker build -t compliance-platform .

# Run locally
docker run -p 8501:8501 \
  -e DATABASE_URL="postgresql://admin:admin@host.docker.internal:5433/compliance_new_db" \
  compliance-platform
```

### Docker Compose (Full Stack)

```bash
# Start app and database together
docker-compose up --build

# Access at http://localhost:8501
```

The Docker Compose setup starts PostgreSQL on port 5433 (external) to avoid conflicts with other local PostgreSQL instances.
