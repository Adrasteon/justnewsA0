-- Migration: 005_create_synthesized_articles_table.sql
-- Description: Create a dedicated `synthesized_articles` table (Option B)
-- Created: 2025-11-20

CREATE TABLE IF NOT EXISTS synthesized_articles (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    story_id VARCHAR(255) NOT NULL UNIQUE,
    cluster_id VARCHAR(255) NULL,
    input_articles JSON NULL,
    title TEXT NULL,
    body LONGTEXT NULL,
    summary TEXT NULL,
    reasoning_plan JSON NULL,
    analysis_summary JSON NULL,
    synth_metadata JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_published BOOLEAN DEFAULT FALSE,
    published_at DATETIME NULL,
    published_by VARCHAR(255) NULL
);

-- DOWN migration (manual) - DROP TABLE synthesized_articles;
