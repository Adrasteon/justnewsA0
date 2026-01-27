-- Migration: 007_add_entities_and_training_examples.sql
-- Description: Ensure entities, article_entities, training_examples and model_metrics exist (MariaDB)
-- Created: 2025-11-21

CREATE TABLE IF NOT EXISTS entities (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    confidence_score DECIMAL(5,3),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_entity (name, entity_type)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS article_entities (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT NOT NULL,
    entity_id BIGINT NOT NULL,
    relevance_score DECIMAL(5,3),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_article_entity (article_id, entity_id),
    CONSTRAINT fk_article_fk FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    CONSTRAINT fk_entity_fk FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS training_examples (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT NULL,
    task VARCHAR(255) NULL,
    input LONGTEXT NULL,
    input_text LONGTEXT NULL,
    output LONGTEXT NULL,
    output_label VARCHAR(100) NULL,
    model_version VARCHAR(50) NULL,
    confidence_score DECIMAL(5,3) NULL,
    critique TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_training_article FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS model_metrics (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10,4),
    dataset_size INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_metric (model_name, model_version, metric_name, created_at)
) ENGINE=InnoDB;

-- NOTE: Down migrations are not included here; DB admins can DROP the tables if a rollback is required.
