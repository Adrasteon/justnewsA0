-- HITL service base schema migration
BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS hitl_candidates (
    id TEXT PRIMARY KEY,
    url TEXT,
    site_id TEXT,
    extracted_title TEXT,
    extracted_text TEXT,
    raw_html_ref TEXT,
    features TEXT,
    candidate_ts TEXT,
    crawler_job_id TEXT,
    status TEXT,
    ingestion_priority INTEGER DEFAULT 0,
    suggested_label TEXT,
    suggested_confidence REAL
);

CREATE TABLE IF NOT EXISTS hitl_labels (
    id TEXT PRIMARY KEY,
    candidate_id TEXT,
    label TEXT,
    cleaned_text TEXT,
    annotator_id TEXT,
    created_at TEXT,
    source TEXT,
    treat_as_valid INTEGER DEFAULT 0,
    needs_cleanup INTEGER DEFAULT 0,
    qa_sampled INTEGER DEFAULT 0,
    ingest_enqueued_at TEXT,
    ingestion_status TEXT
);

CREATE TABLE IF NOT EXISTS hitl_qa_queue (
    id TEXT PRIMARY KEY,
    label_id TEXT,
    candidate_id TEXT,
    created_at TEXT,
    review_status TEXT,
    reviewer_id TEXT,
    notes TEXT,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_hitl_candidates_status_ts
    ON hitl_candidates (status, candidate_ts);

CREATE INDEX IF NOT EXISTS idx_hitl_labels_candidate
    ON hitl_labels (candidate_id);

CREATE INDEX IF NOT EXISTS idx_hitl_labels_created_at
    ON hitl_labels (created_at);

CREATE INDEX IF NOT EXISTS idx_hitl_qa_queue_status
    ON hitl_qa_queue (review_status, created_at);

COMMIT;
