-- Adds timestamp column tracking when a request's creation email was sent.
-- Used by services/mailer to enforce idempotency (skip send if already notified).
--
-- Safe to re-run: IF NOT EXISTS guard in PostgreSQL 9.6+.
ALTER TABLE requests ADD COLUMN IF NOT EXISTS email_notified_at TIMESTAMP NULL;
