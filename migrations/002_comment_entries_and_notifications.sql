-- Migration 002: Add comment_entries and notifications tables
-- Date: 2026-04-11
-- Purpose: B1 (threaded comments with attribution) + A2 (in-app notifications)

-- Comment entries: threaded comments with author, timestamp, and optional image
CREATE TABLE IF NOT EXISTS comment_entries (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    author_email VARCHAR(255) NOT NULL,
    author_name VARCHAR(255),
    content TEXT NOT NULL,
    entry_type VARCHAR(50) DEFAULT 'comment',
    image_drive_link TEXT,
    image_file_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notifications: in-app alerts for status changes
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for new tables
CREATE INDEX IF NOT EXISTS idx_comment_entries_request_id ON comment_entries(request_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_email ON notifications(user_email);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);

-- Indexes for audit_log performance
CREATE INDEX IF NOT EXISTS idx_audit_log_entity_id ON audit_log(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);

-- Fix: internal_registration.status_id missing ON DELETE SET NULL
-- (cannot ALTER FK in PostgreSQL, but new deployments will use init_db.sql)
