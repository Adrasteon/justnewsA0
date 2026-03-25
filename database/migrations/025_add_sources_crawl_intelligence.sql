-- 025_add_sources_crawl_intelligence.sql
-- Add lean crawler intelligence fields to the sources table.
-- These fields guide scheduling and fallback behavior without storing bulky payloads.

ALTER TABLE sources
    ADD COLUMN last_crawl_outcome VARCHAR(32) NULL,
    ADD COLUMN last_candidate_count INT NOT NULL DEFAULT 0,
    ADD COLUMN crawl_fail_streak INT NOT NULL DEFAULT 0,
    ADD COLUMN crawl_blocked_until DATETIME NULL,
    ADD COLUMN crawl_quality_score DOUBLE NOT NULL DEFAULT 0.0;

CREATE INDEX idx_sources_crawl_blocked_until
    ON sources (crawl_blocked_until);

CREATE INDEX idx_sources_crawl_quality
    ON sources (crawl_quality_score);

CREATE INDEX idx_sources_last_crawl_outcome
    ON sources (last_crawl_outcome);

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at)
VALUES ('025_add_sources_crawl_intelligence', NOW());
