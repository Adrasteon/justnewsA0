-- Migration: 010_canonical_schema_fix.sql
-- Description: Unify schema with application requirements (analyzed, source_id, result size)
-- Created: 2026-01-27
-- Author: JustNews Setup

-- UP: Apply schema fixes

-- 1. Ensure `analyzed` column exists in articles
-- This column is used to track if an article has been processed by the Analyst agent
ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS analyzed TINYINT(1) DEFAULT 0;

-- 2. Ensure `source_id` column exists in articles
-- This helps link articles back to specific source definitions if needed
ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS source_id INT DEFAULT NULL;

-- 3. Widen `crawler_jobs.result` to LONGTEXT
-- The default TEXT (64KB) is insufficient for large batch crawls (e.g. 600+ articles)
ALTER TABLE crawler_jobs
    MODIFY result LONGTEXT;

-- DOWN: Revert changes (Warning: Potential Data Loss)

-- ALTER TABLE crawler_jobs MODIFY result TEXT;
-- ALTER TABLE articles DROP COLUMN source_id;
-- ALTER TABLE articles DROP COLUMN analyzed;
