-- Migration: 008_add_kg_audit_and_entity_columns.sql
-- Description: Add KG audit table and normalize entity storage schema
-- Created: 2025-11-21

-- Add canonical_name and detection_source columns to entities (if not present)
ALTER TABLE entities
    ADD COLUMN IF NOT EXISTS canonical_name VARCHAR(255) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS detection_source VARCHAR(128) DEFAULT NULL;

-- Create a KG audit table for operations and access logs
CREATE TABLE IF NOT EXISTS kg_audit (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    operation VARCHAR(50) NOT NULL,
    actor VARCHAR(255) DEFAULT NULL,
    target_type VARCHAR(50) DEFAULT NULL,
    target_id BIGINT DEFAULT NULL,
    details JSON DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Note: No down migrations provided here. Admins can DROP columns/tables if needed.
