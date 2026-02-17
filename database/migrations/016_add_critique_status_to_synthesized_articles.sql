-- Migration: 016_add_critique_status_to_synthesized_articles.sql
-- Description: Add critique_status column to synthesized_articles table for workflow orchestration
-- Created: 2026-02-10
-- NOTE: This column is required by the workflow orchestrator (agents/workflow_orchestrator.py)
--       to check and route articles through the critique/review stage

-- UP: Add critique_status column
ALTER TABLE synthesized_articles
    ADD COLUMN IF NOT EXISTS critique_status VARCHAR(50) DEFAULT 'pending';

-- Add index on critique_status for efficient filtering
CREATE INDEX IF NOT EXISTS idx_synthesized_articles_critique_status ON synthesized_articles(critique_status);

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at) VALUES ('016_add_critique_status_to_synthesized_articles', NOW());

-- DOWN: Remove critique_status column (uncomment to revert)
-- ALTER TABLE synthesized_articles DROP COLUMN critique_status;
-- DROP INDEX idx_synthesized_articles_critique_status ON synthesized_articles;
