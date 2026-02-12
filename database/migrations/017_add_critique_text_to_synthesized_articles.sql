-- Migration: 017_add_critique_text_to_synthesized_articles.sql
-- Description: Add critique_text column to synthesized_articles table to store results from the Critic agent
-- Created: 2026-02-10

-- UP: Add critique_text column
ALTER TABLE synthesized_articles
    ADD COLUMN IF NOT EXISTS critique_text LONGTEXT AFTER critique_status;

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at) VALUES ('017_add_critique_text_to_synthesized_articles', NOW());
