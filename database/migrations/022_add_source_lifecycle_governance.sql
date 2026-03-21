-- Migration: 022_add_source_lifecycle_governance.sql
-- Description: Add source lifecycle state fields and transition audit history
-- Created: 2026-03-21

ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS source_state VARCHAR(64) NOT NULL DEFAULT 'trusted_whitelist',
    ADD COLUMN IF NOT EXISTS source_state_reason VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS source_state_updated_at DATETIME NULL,
    ADD COLUMN IF NOT EXISTS source_state_score_version VARCHAR(64) NULL,
    ADD COLUMN IF NOT EXISTS source_owner_group VARCHAR(255) NULL;

UPDATE sources
SET source_state_updated_at = COALESCE(source_state_updated_at, updated_at, created_at, NOW())
WHERE source_state_updated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sources_source_state ON sources(source_state);
CREATE INDEX IF NOT EXISTS idx_sources_state_updated_at ON sources(source_state_updated_at);

CREATE TABLE IF NOT EXISTS source_state_transitions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    source_id INT NOT NULL,
    previous_state VARCHAR(64) NULL,
    new_state VARCHAR(64) NOT NULL,
    reason_code VARCHAR(255) NULL,
    actor VARCHAR(128) NULL,
    details JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_source_state_transitions_source FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
    INDEX idx_source_state_transitions_source_id (source_id),
    INDEX idx_source_state_transitions_new_state (new_state),
    INDEX idx_source_state_transitions_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO schema_migrations (version, applied_at) VALUES ('022_add_source_lifecycle_governance', NOW());