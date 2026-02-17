-- Migration: 015_add_last_crawl_at_to_sources.sql
-- Description: Add last_crawl_at column to sources table to track when sources were last crawled
-- Created: 2026-02-10
-- NOTE: This column is required by the crawler (agents/crawler/crawler_engine.py)
--       to track and manage source crawl frequency

-- UP: Add last_crawl_at column
ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS last_crawl_at TIMESTAMP NULL DEFAULT NULL;

-- Add index on last_crawl_at for efficient filtering
CREATE INDEX IF NOT EXISTS idx_sources_last_crawl_at ON sources(last_crawl_at);

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at) VALUES ('015_add_last_crawl_at_to_sources', NOW());

-- DOWN: Remove last_crawl_at column (uncomment to revert)
-- ALTER TABLE sources DROP COLUMN last_crawl_at;
-- DROP INDEX idx_sources_last_crawl_at ON sources;
