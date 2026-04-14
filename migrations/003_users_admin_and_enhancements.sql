-- Migration 003: Users admin table, Inside Sales assignments, Request attachments, Reminder schedule, Case ID
-- Date: 2026-04-14
-- Purpose: F1/F2/F3/F4/F5/F7 — user management from UI, case IDs, attachments, reminders
--
-- Design notes:
-- - `users.email` is the PK. Immutable assumption for MVP.
-- - `inside_sales_comerciales` is a many-to-many link table (an IS can support several comerciales).
-- - `case_id` generated in Python (see database/crud/clientes.py:format_case_id).
--   Backfill at end of migration covers historical rows.
-- - `request_attachments` stores Drive URLs for the new "Adjuntos Solicitud" subfolder.
-- - `reminder_schedule` drives the on-page-load reminder dispatcher.

-- ---------------------------------------------------------------------------
-- F1: users table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    email VARCHAR(255) PRIMARY KEY,
    nombre_display VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL CHECK (rol IN ('comercial','inside_sales','compliance','otro')),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_users_rol ON users(rol);
CREATE INDEX IF NOT EXISTS idx_users_activo ON users(activo);

-- ---------------------------------------------------------------------------
-- F1: inside_sales_comerciales (many-to-many)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inside_sales_comerciales (
    inside_sales_email VARCHAR(255) NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    comercial_email    VARCHAR(255) NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    assigned_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by        VARCHAR(255),
    PRIMARY KEY (inside_sales_email, comercial_email)
);

CREATE INDEX IF NOT EXISTS idx_isc_inside_sales ON inside_sales_comerciales(inside_sales_email);
CREATE INDEX IF NOT EXISTS idx_isc_comercial ON inside_sales_comerciales(comercial_email);

-- ---------------------------------------------------------------------------
-- F2: submitted_by_email on requests (Inside Sales attribution)
-- ---------------------------------------------------------------------------
ALTER TABLE requests ADD COLUMN IF NOT EXISTS submitted_by_email VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_requests_submitted_by_email ON requests(submitted_by_email);

-- ---------------------------------------------------------------------------
-- F4: notes on requests (free-text for compliance) + attachments table
-- ---------------------------------------------------------------------------
ALTER TABLE requests ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE TABLE IF NOT EXISTS request_attachments (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    drive_link TEXT NOT NULL,
    uploaded_by VARCHAR(255) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_request_attachments_request_id ON request_attachments(request_id);

-- ---------------------------------------------------------------------------
-- F5: case_id on requests (C0001, C0002, ... backfilled below)
-- ---------------------------------------------------------------------------
ALTER TABLE requests ADD COLUMN IF NOT EXISTS case_id VARCHAR(10);

-- UNIQUE constraint added as a separate index so it tolerates existing NULLs
-- during backfill (before the UPDATE below, all are NULL and partial unique
-- index with WHERE case_id IS NOT NULL handles this cleanly).
CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_case_id_unique
    ON requests(case_id) WHERE case_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- F7: reminder_max_months on requests + reminder_schedule table
-- ---------------------------------------------------------------------------
ALTER TABLE requests ADD COLUMN IF NOT EXISTS reminder_max_months INTEGER;

CREATE TABLE IF NOT EXISTS reminder_schedule (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    next_reminder_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    frequency_days INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reminder_schedule_next
    ON reminder_schedule(next_reminder_at) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_reminder_schedule_request_id
    ON reminder_schedule(request_id);

-- ---------------------------------------------------------------------------
-- F5 BACKFILL: populate case_id for historical rows
-- Idempotent: only touches rows where case_id IS NULL.
-- Safe against concurrent writes because it filters on NULL state.
-- ---------------------------------------------------------------------------
UPDATE requests
   SET case_id = 'C' || LPAD(id::text, 4, '0')
 WHERE case_id IS NULL;
