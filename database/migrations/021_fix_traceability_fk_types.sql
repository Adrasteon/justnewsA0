-- Migration: 021_fix_traceability_fk_types.sql
-- Description: Fix traceability FK column types to match canonical int article/entity ids
-- Created: 2026-03-20

CREATE TABLE IF NOT EXISTS statements (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    article_id INT NOT NULL,
    story_id VARCHAR(255) NULL,
    source_url VARCHAR(1024) NULL,
    source_domain VARCHAR(255) NULL,
    speaker_entity_id INT NULL,
    attribution_text TEXT NULL,
    statement_text LONGTEXT NOT NULL,
    span_start INT NULL,
    span_end INT NULL,
    extraction_method VARCHAR(128) NULL,
    confidence DECIMAL(5,3) NULL,
    perspective_label VARCHAR(64) NULL,
    is_opinion BOOLEAN NOT NULL DEFAULT FALSE,
    counts_as_factual_corroboration BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_statements_article FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    CONSTRAINT fk_statements_speaker_entity FOREIGN KEY (speaker_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
    INDEX idx_statements_article_id (article_id),
    INDEX idx_statements_story_id (story_id),
    INDEX idx_statements_speaker_entity_id (speaker_entity_id),
    INDEX idx_statements_source_domain (source_domain)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS quotes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    article_id INT NOT NULL,
    story_id VARCHAR(255) NULL,
    source_url VARCHAR(1024) NULL,
    source_domain VARCHAR(255) NULL,
    speaker_entity_id INT NULL,
    attribution_text TEXT NULL,
    quote_text LONGTEXT NOT NULL,
    span_start INT NULL,
    span_end INT NULL,
    extraction_method VARCHAR(128) NULL,
    confidence DECIMAL(5,3) NULL,
    perspective_label VARCHAR(64) NULL,
    is_opinion BOOLEAN NOT NULL DEFAULT FALSE,
    counts_as_factual_corroboration BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_quotes_article FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    CONSTRAINT fk_quotes_speaker_entity FOREIGN KEY (speaker_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
    INDEX idx_quotes_article_id (article_id),
    INDEX idx_quotes_story_id (story_id),
    INDEX idx_quotes_speaker_entity_id (speaker_entity_id),
    INDEX idx_quotes_source_domain (source_domain)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS statement_entities (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    statement_id BIGINT UNSIGNED NOT NULL,
    entity_id INT NOT NULL,
    relation_type VARCHAR(64) NULL,
    confidence DECIMAL(5,3) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_statement_entity (statement_id, entity_id, relation_type),
    CONSTRAINT fk_statement_entities_statement FOREIGN KEY (statement_id) REFERENCES statements(id) ON DELETE CASCADE,
    CONSTRAINT fk_statement_entities_entity FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    INDEX idx_statement_entities_entity_id (entity_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS quote_entities (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    quote_id BIGINT UNSIGNED NOT NULL,
    entity_id INT NOT NULL,
    relation_type VARCHAR(64) NULL,
    confidence DECIMAL(5,3) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_quote_entity (quote_id, entity_id, relation_type),
    CONSTRAINT fk_quote_entities_quote FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE,
    CONSTRAINT fk_quote_entities_entity FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    INDEX idx_quote_entities_entity_id (entity_id)
) ENGINE=InnoDB;