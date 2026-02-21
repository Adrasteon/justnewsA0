-- Migration: 019_align_training_examples_for_online_training.sql
-- Description: Align legacy training_examples table with online training coordinator fields
-- Created: 2026-02-20

ALTER TABLE training_examples
    ADD COLUMN agent_name VARCHAR(128) NULL AFTER article_id,
    ADD COLUMN task_type VARCHAR(128) NULL AFTER agent_name,
    ADD COLUMN expected_output LONGTEXT NULL AFTER input_text,
    ADD COLUMN uncertainty_score DECIMAL(5,3) NULL AFTER confidence_score,
    ADD COLUMN importance_score DECIMAL(5,3) NULL AFTER uncertainty_score,
    ADD COLUMN source_url VARCHAR(1024) NULL AFTER importance_score,
    ADD COLUMN `timestamp` DATETIME NULL AFTER source_url,
    ADD COLUMN user_feedback TEXT NULL AFTER `timestamp`,
    ADD COLUMN correction_priority INT NULL DEFAULT 0 AFTER user_feedback;

-- Optional backfill from legacy fields where available
UPDATE training_examples
SET
    task_type = COALESCE(task_type, task),
    expected_output = COALESCE(expected_output, output)
WHERE task_type IS NULL OR expected_output IS NULL;

CREATE INDEX idx_training_examples_agent_task ON training_examples(agent_name, task_type);
CREATE INDEX idx_training_examples_timestamp ON training_examples(`timestamp`);
