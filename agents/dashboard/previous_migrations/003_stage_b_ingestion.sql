-- Migration: 003_stage_b_ingestion.sql
-- Description: Stage B ingestion pipeline enhancements
-- Created: 2025-10-26
-- Author: GitHub Copilot

-- NOTE: This migration targets PostgreSQL and uses Postgres-specific
-- types and features (JSONB, array types, partial indexes). It is NOT
-- compatible with MariaDB. Convert to MariaDB-compatible SQL before applying.

-- UP: Extend articles table with ingestion metadata and embedding storage

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS normalized_url VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS url_hash VARCHAR(128),
    ADD COLUMN IF NOT EXISTS url_hash_algo VARCHAR(32) DEFAULT 'sha256',
    ADD COLUMN IF NOT EXISTS language VARCHAR(16),
    ADD COLUMN IF NOT EXISTS section VARCHAR(255),
    ADD COLUMN IF NOT EXISTS tags TEXT[],
    ADD COLUMN IF NOT EXISTS authors JSONB,
    ADD COLUMN IF NOT EXISTS raw_html_ref VARCHAR(1024),
    ADD COLUMN IF NOT EXISTS extraction_confidence DECIMAL(4,3),
    ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS review_reasons JSONB,
    ADD COLUMN IF NOT EXISTS extraction_metadata JSONB,
    ADD COLUMN IF NOT EXISTS structured_metadata JSONB,
    ADD COLUMN IF NOT EXISTS publication_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS metadata JSONB,
    ADD COLUMN IF NOT EXISTS collection_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS embedding DOUBLE PRECISION[];

CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_normalized_url
    ON articles (normalized_url) WHERE normalized_url IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url_hash
    ON articles (url_hash) WHERE url_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_articles_publication_date
    ON articles (publication_date);

-- DOWN MIGRATION INSTRUCTIONS (manual execution only)
--
-- DROP INDEX IF EXISTS idx_articles_publication_date;
-- DROP INDEX IF EXISTS idx_articles_url_hash;
-- DROP INDEX IF EXISTS idx_articles_normalized_url;
--
-- ALTER TABLE articles
--     DROP COLUMN IF EXISTS embedding,
--     DROP COLUMN IF EXISTS collection_timestamp,
--     DROP COLUMN IF EXISTS publication_date,
--     DROP COLUMN IF EXISTS metadata,
--     DROP COLUMN IF EXISTS structured_metadata,
--     DROP COLUMN IF EXISTS extraction_metadata,
--     DROP COLUMN IF EXISTS review_reasons,
--     DROP COLUMN IF EXISTS needs_review,
--     DROP COLUMN IF EXISTS extraction_confidence,
--     DROP COLUMN IF EXISTS raw_html_ref,
--     DROP COLUMN IF EXISTS authors,
--     DROP COLUMN IF EXISTS tags,
--     DROP COLUMN IF EXISTS section,
--     DROP COLUMN IF EXISTS language,
--     DROP COLUMN IF EXISTS url_hash_algo,
--     DROP COLUMN IF EXISTS url_hash,
--     DROP COLUMN IF EXISTS normalized_url;
