-- Migration 007: drop NOT NULL on registration.doc_type_id
-- Date: 2026-04-20
-- Purpose: align production with init_db.sql after a prod-only schema drift.
--
-- Incident: on 2026-04-20 users hit
--   psycopg2.errors.NotNullViolation: null value in column "doc_type_id"
--   of relation "registration" violates not-null constraint
-- when saving the upload-documents form without attaching any files.
--
-- Root cause: production had a NOT NULL constraint on
-- ``registration.doc_type_id`` that was never present in init_db.sql.
-- The CRUD ``upsert_request_info`` relies on that column being nullable
-- to insert a placeholder row holding request-level metadata
-- (``razon_social`` / ``fecha_creacion``) before any documents exist.
--
-- ``ALTER COLUMN ... DROP NOT NULL`` is a no-op if the column is already
-- nullable, so this migration is idempotent and safe to re-run.

ALTER TABLE registration
    ALTER COLUMN doc_type_id DROP NOT NULL;
