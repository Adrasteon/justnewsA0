-- Migration: 011_ensure_sources_last_verified.sql
-- Description: Ensure last_verified column exists on sources table
-- Created: 2026-02-08
-- Author: GitHub Copilot

-- UP: Add last_verified column if it doesn't exist

ALTER TABLE sources
ADD COLUMN IF NOT EXISTS last_verified DATETIME DEFAULT NULL;

-- DOWN: Remove the column (manual execution only if needed)

-- ALTER TABLE sources DROP COLUMN IF EXISTS last_verified;
