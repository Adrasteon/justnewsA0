-- 024_add_taxonomy_drift_events.sql
-- Add taxonomy drift monitoring events for living-story publish feedback loop.

CREATE TABLE IF NOT EXISTS news_taxonomy_drift_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    story_id VARCHAR(64) NOT NULL,
    cluster_id VARCHAR(64) NULL,
    observed_category VARCHAR(64) NOT NULL,
    expected_category VARCHAR(64) NULL,
    lane VARCHAR(64) NULL,
    drift_score DECIMAL(8, 4) NOT NULL,
    threshold_score DECIMAL(8, 4) NOT NULL,
    llm_review_invoked TINYINT(1) NOT NULL DEFAULT 0,
    llm_adjusted TINYINT(1) NOT NULL DEFAULT 0,
    final_category VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    metadata JSON NULL,
    occurred_at DATETIME NOT NULL,
    INDEX idx_news_taxonomy_drift_story (story_id),
    INDEX idx_news_taxonomy_drift_cluster (cluster_id),
    INDEX idx_news_taxonomy_drift_occurred_at (occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at)
VALUES ('024_add_taxonomy_drift_events', NOW());
