-- Migration: 009_create_sources_table.sql
-- Description: Create sources table for managing news sources
-- Created: 2026-01-26
-- NOTE: last_crawl_at column is added by migration 015_add_last_crawl_at_to_sources.sql

CREATE TABLE IF NOT EXISTS sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    domain VARCHAR(255) UNIQUE,
    url VARCHAR(500),
    name VARCHAR(255),
    description TEXT,
    country VARCHAR(10),
    language VARCHAR(10),
    last_verified DATETIME,
    paywall BOOLEAN DEFAULT FALSE,
    paywall_type VARCHAR(50),
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add index on domain for fast lookups
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);
-- Add index on country and language for filtering
CREATE INDEX IF NOT EXISTS idx_sources_country_lang ON sources(country, language);
