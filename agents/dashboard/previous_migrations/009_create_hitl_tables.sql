-- Migration 009: Create HITL tables using MariaDB syntax

-- Table: hitl_candidates
CREATE TABLE IF NOT EXISTS hitl_candidates (
    id VARCHAR(255) NOT NULL,
    url TEXT,
    site_id VARCHAR(255),
    extracted_title TEXT,
    extracted_text LONGTEXT,
    raw_html_ref TEXT,
    features TEXT, -- JSON stored as text
    candidate_ts VARCHAR(255),
    crawler_job_id VARCHAR(255),
    status VARCHAR(50),
    ingestion_priority INT DEFAULT 0,
    suggested_label VARCHAR(50),
    suggested_confidence FLOAT,
    PRIMARY KEY (id)
);

-- Table: hitl_labels
CREATE TABLE IF NOT EXISTS hitl_labels (
    id VARCHAR(255) NOT NULL,
    candidate_id VARCHAR(255),
    label VARCHAR(50),
    cleaned_text LONGTEXT,
    annotator_id VARCHAR(255),
    created_at VARCHAR(255),
    source VARCHAR(255),
    treat_as_valid TINYINT(1) DEFAULT 0,
    needs_cleanup TINYINT(1) DEFAULT 0,
    qa_sampled TINYINT(1) DEFAULT 0,
    ingest_enqueued_at VARCHAR(255),
    ingestion_status VARCHAR(50),
    PRIMARY KEY (id)
);

-- Table: hitl_qa_queue
CREATE TABLE IF NOT EXISTS hitl_qa_queue (
    id VARCHAR(255) NOT NULL,
    label_id VARCHAR(255),
    candidate_id VARCHAR(255),
    created_at VARCHAR(255),
    review_status VARCHAR(50),
    reviewer_id VARCHAR(255),
    notes TEXT,
    reviewed_at VARCHAR(255),
    PRIMARY KEY (id)
);

-- Indexes
-- idx_hitl_candidates_status_ts
CREATE INDEX idx_hitl_candidates_status_ts ON hitl_candidates (status, candidate_ts);

-- idx_hitl_labels_created_at
CREATE INDEX idx_hitl_labels_created_at ON hitl_labels (created_at);

-- idx_hitl_qa_queue_status
CREATE INDEX idx_hitl_qa_queue_status ON hitl_qa_queue (review_status, created_at);
