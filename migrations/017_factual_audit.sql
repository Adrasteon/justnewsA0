-- Migration: Factual Audit Schema Extensions
-- Adds columns for 5-point fact checking scores

ALTER TABLE articles ADD COLUMN factual_accuracy_score FLOAT DEFAULT NULL;
ALTER TABLE articles ADD COLUMN fact_check_details JSON DEFAULT NULL;
