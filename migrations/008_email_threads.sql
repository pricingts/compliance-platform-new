-- Migration 007: threading persistence for compliance mailer.
-- Stores Gmail threadId + Message-ID chain per request so subsequent events
-- (reminders, status changes) can thread into the same Gmail conversation.
--
-- Safe to re-run: IF NOT EXISTS guards. Idempotent.
CREATE TABLE IF NOT EXISTS email_threads (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL UNIQUE REFERENCES requests(id) ON DELETE CASCADE,
    gmail_thread_id VARCHAR(255),
    last_message_id VARCHAR(512),
    references_chain TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_email_threads_request_id ON email_threads(request_id);
CREATE INDEX IF NOT EXISTS idx_email_threads_gmail_thread_id ON email_threads(gmail_thread_id);
