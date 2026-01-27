-- Migration: 002_add_sentiment_analysis.sql
-- Description: Add sentiment analysis tables and columns
-- Created: 2024-01-02
-- Author: Database Team

-- NOTE: This migration targets PostgreSQL and uses Postgres-specific
-- types (SERIAL, JSONB, arrays). It is NOT compatible with MariaDB and
-- should not be applied to MariaDB deployments without conversion.

-- UP: Add sentiment analysis features

-- Add sentiment columns to articles table
ALTER TABLE articles
ADD COLUMN IF NOT EXISTS sentiment_score DECIMAL(3,2),
ADD COLUMN IF NOT EXISTS sentiment_label VARCHAR(20),
ADD COLUMN IF NOT EXISTS sentiment_confidence DECIMAL(3,2);

-- Create sentiment_analysis table for detailed analysis
CREATE TABLE IF NOT EXISTS sentiment_analysis (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    analyzer_version VARCHAR(50) NOT NULL,
    overall_sentiment VARCHAR(20) NOT NULL,
    overall_confidence DECIMAL(3,2),
    positive_score DECIMAL(3,2),
    negative_score DECIMAL(3,2),
    neutral_score DECIMAL(3,2),
    analysis_metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for sentiment analysis
CREATE INDEX IF NOT EXISTS idx_sentiment_analysis_article_id ON sentiment_analysis(article_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_analysis_overall_sentiment ON sentiment_analysis(overall_sentiment);
CREATE INDEX IF NOT EXISTS idx_sentiment_analysis_created_at ON sentiment_analysis(created_at);

-- Create article_sentiment_summary table for caching
CREATE TABLE IF NOT EXISTS article_sentiment_summary (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    summary_text TEXT,
    key_points TEXT[],
    sentiment_trend VARCHAR(20),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(article_id)
);

-- Create bias_analysis table
CREATE TABLE IF NOT EXISTS bias_analysis (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    bias_score DECIMAL(3,2),
    bias_category VARCHAR(50),
    confidence_score DECIMAL(3,2),
    detected_biases TEXT[],
    analysis_metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for bias analysis
CREATE INDEX IF NOT EXISTS idx_bias_analysis_article_id ON bias_analysis(article_id);
CREATE INDEX IF NOT EXISTS idx_bias_analysis_bias_category ON bias_analysis(bias_category);

-- Update articles table with sentiment index
CREATE INDEX IF NOT EXISTS idx_articles_sentiment_score ON articles(sentiment_score);
CREATE INDEX IF NOT EXISTS idx_articles_sentiment_label ON articles(sentiment_label);

-- DOWN: Remove sentiment analysis features

DROP INDEX IF EXISTS idx_articles_sentiment_label;
DROP INDEX IF EXISTS idx_articles_sentiment_score;

DROP TABLE IF EXISTS bias_analysis;
DROP TABLE IF EXISTS article_sentiment_summary;
DROP TABLE IF EXISTS sentiment_analysis;

ALTER TABLE articles
DROP COLUMN IF EXISTS sentiment_confidence,
DROP COLUMN IF EXISTS sentiment_label,
DROP COLUMN IF EXISTS sentiment_score;