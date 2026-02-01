-- Migration: 009_b_create_crawler_jobs.sql
-- Description: Create crawler_jobs table which was missing in initial migrations
-- Created: 2026-01-31

CREATE TABLE IF NOT EXISTS crawler_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(50) DEFAULT 'pending',
    result TEXT,
    error TEXT,
    source_url VARCHAR(1000),
    job_type VARCHAR(50) DEFAULT 'crawl',
    options JSON,
    error_message TEXT, 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_crawler_jobs_status ON crawler_jobs(status);
