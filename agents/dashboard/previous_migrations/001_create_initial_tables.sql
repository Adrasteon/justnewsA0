-- Migration: 001_create_initial_tables.sql
-- Description: Create initial database tables for JustNewsAgent
-- Created: 2024-01-01
-- Author: Database Team

-- NOTE: This migration uses Postgres-specific constructs such as SERIAL,
-- references, and certain extensions. It is preserved for historical
-- purposes and is not directly compatible with MariaDB without
-- conversion. Use MariaDB-specific migrations or the `init_database.py`
-- script which adapts SQL for MariaDB where appropriate.

-- UP: Create initial tables

-- Create articles table
CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    summary TEXT,
    author VARCHAR(255),
    source_url VARCHAR(1000) UNIQUE,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for articles
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_author ON articles(author);
CREATE INDEX IF NOT EXISTS idx_articles_source_url ON articles(source_url);

-- Create entities table
CREATE TABLE IF NOT EXISTS entities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL, -- PERSON, ORGANIZATION, LOCATION, etc.
    confidence_score DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, entity_type)
);

-- Create article_entities junction table
CREATE TABLE IF NOT EXISTS article_entities (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relevance_score DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(article_id, entity_id)
);

-- Create training_examples table for ML training
CREATE TABLE IF NOT EXISTS training_examples (
    id SERIAL PRIMARY KEY,
    article_id INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    input_text TEXT NOT NULL,
    output_label VARCHAR(100),
    model_version VARCHAR(50),
    confidence_score DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for training examples
CREATE INDEX IF NOT EXISTS idx_training_examples_model_version ON training_examples(model_version);
CREATE INDEX IF NOT EXISTS idx_training_examples_created_at ON training_examples(created_at);

-- Create model_metrics table for tracking performance
CREATE TABLE IF NOT EXISTS model_metrics (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10,4),
    dataset_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(model_name, model_version, metric_name, created_at)
);

-- DOWN: Drop initial tables

DROP TABLE IF EXISTS model_metrics;
DROP TABLE IF EXISTS training_examples;
DROP TABLE IF EXISTS article_entities;
DROP TABLE IF EXISTS entities;
DROP TABLE IF EXISTS articles;