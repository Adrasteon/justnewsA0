-- Migration: 004_add_synthesis_fields.sql
-- Description: Add synthesis & publishing metadata to `articles` table (Option A)
-- Created: 2025-11-20
-- Note: This migration targets MariaDB/MySQL. Use JSON or TEXT if needed.

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS is_synthesized BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS input_cluster_ids JSON DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS synth_model VARCHAR(255) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS synth_version VARCHAR(255) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS synth_prompt_id VARCHAR(255) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS synth_trace JSON DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS critic_result JSON DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS fact_check_status VARCHAR(32) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS fact_check_trace JSON DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS published_at DATETIME NULL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(255) DEFAULT NULL;

-- DOWN migration (manual): use ALTER TABLE ... DROP COLUMN

