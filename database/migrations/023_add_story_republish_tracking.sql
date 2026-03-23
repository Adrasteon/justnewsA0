-- 023_add_story_republish_tracking.sql
-- Ensure publisher rows can be deterministically replaced by story/cluster
-- and persist explicit republish events for auditability.

ALTER TABLE news_article
    ADD COLUMN IF NOT EXISTS story_id VARCHAR(64) NULL,
    ADD COLUMN IF NOT EXISTS source_cluster_id VARCHAR(64) NULL;

CREATE INDEX IF NOT EXISTS idx_news_article_story_id
    ON news_article (story_id);

CREATE INDEX IF NOT EXISTS idx_news_article_source_cluster_id
    ON news_article (source_cluster_id);

CREATE TABLE IF NOT EXISTS news_story_republish_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    story_id VARCHAR(64) NOT NULL,
    cluster_id VARCHAR(64) NULL,
    news_article_id BIGINT NULL,
    action VARCHAR(32) NOT NULL,
    replaced_existing TINYINT(1) NOT NULL DEFAULT 0,
    synthesized_created_at DATETIME NULL,
    synthesized_updated_at DATETIME NULL,
    previous_news_updated_at DATETIME NULL,
    occurred_at DATETIME NOT NULL,
    metadata JSON NULL,
    INDEX idx_news_story_republish_events_story_id (story_id),
    INDEX idx_news_story_republish_events_cluster_id (cluster_id),
    INDEX idx_news_story_republish_events_occurred_at (occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at)
VALUES ('023_add_story_republish_tracking', NOW());
