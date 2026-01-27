-- Migration: 006_create_synthesizer_jobs_table.sql
-- Description: Create a synthesizer_jobs table to persist synthesis job lifecycle
-- Created: 2025-11-20

CREATE TABLE IF NOT EXISTS synthesizer_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    result TEXT NULL,
    error TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- DOWN migration (manual): DROP TABLE synthesized_jobs;
