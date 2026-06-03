-- Migration 010: widen requests.email from VARCHAR(255) to TEXT.
-- Date: 2026-06-03
-- Purpose: the client contact field must hold several comma/semicolon-separated
--   emails (a comercial can register more than one contact). VARCHAR(255) risked
--   silently truncating a multi-email string mid-address.
--
-- Safe + idempotent: ALTER ... TYPE TEXT is a no-op if the column is already
-- TEXT, and widening never truncates existing data. No USING clause needed
-- because every VARCHAR value is a valid TEXT value.
ALTER TABLE requests ALTER COLUMN email TYPE TEXT;
