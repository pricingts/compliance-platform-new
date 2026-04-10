# Dev Database Setup

## Overview

The compliance platform uses two PostgreSQL databases:
- **Production**: Hosted on Railway, used by the deployed application
- **Development**: Hosted on Railway (separate instance), used for local development and testing

## Creating the Dev Database on Railway

### 1. Create a new PostgreSQL service

```bash
# Login to Railway
railway login

# Create a new project or use existing
railway link

# Add a new PostgreSQL plugin
railway add --plugin postgresql
```

Or via the Railway dashboard:
1. Go to your project in Railway
2. Click "New" > "Database" > "Add PostgreSQL"
3. Name it `compliance-dev-db`

### 2. Get the connection string

```bash
railway variables --service compliance-dev-db
# Look for DATABASE_URL
```

### 3. Copy production schema to dev

```bash
# Export production schema (structure only, no data)
pg_dump --schema-only "$PRODUCTION_DATABASE_URL" > schema_dump.sql

# Import to dev database
psql "$DEV_DATABASE_URL" < schema_dump.sql
```

### 4. Copy seed data (optional)

```bash
# Export only the seed/reference tables
pg_dump --data-only --table=profiles --table=status --table=document_type \
  "$PRODUCTION_DATABASE_URL" > seed_data.sql

# Import seed data to dev
psql "$DEV_DATABASE_URL" < seed_data.sql
```

### 5. Configure local environment

Add the dev database URL to your `.env` file:

```env
DATABASE_URL=postgresql://user:password@host:port/compliance_dev_db
ENV=dev
```

## Environment Detection

The application uses the `ENV` environment variable to determine the environment:
- `dev` - Development (uses DATABASE_URL, relaxed logging)
- `staging` - Staging
- `production` - Production (uses DATABASE_URL from Railway or st.secrets)

## Running Migrations

After setting up the dev database, run Alembic migrations:

```bash
alembic upgrade head
```

## Resetting the Dev Database

To reset the dev database to match production:

```bash
# Drop and recreate
psql "$DEV_DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Re-run migrations
alembic upgrade head

# Re-import seed data
psql "$DEV_DATABASE_URL" < seed_data.sql
```
