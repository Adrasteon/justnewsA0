-- MariaDB initialization script for JustNewsAgent
-- MariaDB initialization script for JustNews
-- Create articles table
CREATE TABLE IF NOT EXISTS articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    summary TEXT,
    author VARCHAR(255),
    source_url VARCHAR(1000) UNIQUE,
    published_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    sentiment_score DECIMAL(3,2),
    sentiment_label VARCHAR(20),
    sentiment_confidence DECIMAL(3,2),
    normalized_url VARCHAR(1000),
    url_hash VARCHAR(128),
    url_hash_algo VARCHAR(32) DEFAULT 'sha256',
    language VARCHAR(16),
    section VARCHAR(255),
    tags JSON,
    authors JSON,
    raw_html_ref VARCHAR(1024),
    extraction_confidence DECIMAL(4,3),
    needs_review BOOLEAN DEFAULT FALSE,
    review_reasons JSON,
    extraction_metadata JSON,
    structured_metadata JSON,
    publication_date TIMESTAMP NULL,
    metadata JSON,
    collection_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Create indexes for articles
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_author ON articles(author);
CREATE INDEX IF NOT EXISTS idx_articles_source_url ON articles(source_url);
CREATE INDEX IF NOT EXISTS idx_articles_sentiment_score ON articles(sentiment_score);
CREATE INDEX IF NOT EXISTS idx_articles_sentiment_label ON articles(sentiment_label);
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_normalized_url ON articles (normalized_url);
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url_hash ON articles (url_hash);
CREATE INDEX IF NOT EXISTS idx_articles_publication_date ON articles (publication_date);

-- Create entities table
CREATE TABLE IF NOT EXISTS entities (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    confidence_score DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_entity (name, entity_type)
) ENGINE=InnoDB;

-- Create article_entities junction table
CREATE TABLE IF NOT EXISTS article_entities (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    article_id BIGINT UNSIGNED NOT NULL,
    entity_id BIGINT UNSIGNED NOT NULL,
    relevance_score DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_article_entity (article_id, entity_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Create training_examples table for ML training
CREATE TABLE IF NOT EXISTS training_examples (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    article_id BIGINT UNSIGNED NULL,
    input_text TEXT NOT NULL,
    output_label VARCHAR(100),
    model_version VARCHAR(50),
    confidence_score DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Create indexes for training examples
CREATE INDEX IF NOT EXISTS idx_training_examples_model_version ON training_examples(model_version);
CREATE INDEX IF NOT EXISTS idx_training_examples_created_at ON training_examples(created_at);

-- Create model_metrics table for tracking performance
CREATE TABLE IF NOT EXISTS model_metrics (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10,4),
    dataset_size INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_metric (model_name, model_version, metric_name, created_at)
) ENGINE=InnoDB;

-- Create sentiment_analysis table for detailed analysis
CREATE TABLE IF NOT EXISTS sentiment_analysis (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    article_id BIGINT UNSIGNED NOT NULL,
    analyzer_version VARCHAR(50) NOT NULL,
    overall_sentiment VARCHAR(20) NOT NULL,
    overall_confidence DECIMAL(3,2),
    positive_score DECIMAL(3,2),
    negative_score DECIMAL(3,2),
    neutral_score DECIMAL(3,2),
    analysis_metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Create indexes for sentiment analysis
CREATE INDEX IF NOT EXISTS idx_sentiment_analysis_article_id ON sentiment_analysis(article_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_analysis_overall_sentiment ON sentiment_analysis(overall_sentiment);
CREATE INDEX IF NOT EXISTS idx_sentiment_analysis_created_at ON sentiment_analysis(created_at);

-- Create article_sentiment_summary table for caching
CREATE TABLE IF NOT EXISTS article_sentiment_summary (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    article_id BIGINT UNSIGNED NOT NULL,
    summary_text TEXT,
    key_points JSON,
    sentiment_trend VARCHAR(20),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_article_summary (article_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Create bias_analysis table
CREATE TABLE IF NOT EXISTS bias_analysis (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    article_id BIGINT UNSIGNED NOT NULL,
    bias_score DECIMAL(3,2),
    bias_category VARCHAR(50),
    confidence_score DECIMAL(3,2),
    detected_biases JSON,
    analysis_metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Create indexes for bias analysis
CREATE INDEX IF NOT EXISTS idx_bias_analysis_article_id ON bias_analysis(article_id);
CREATE INDEX IF NOT EXISTS idx_bias_analysis_bias_category ON bias_analysis(bias_category);
-- Create sources table
CREATE TABLE IF NOT EXISTS sources (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT UNIQUE PRIMARY KEY,
    domain VARCHAR(255) UNIQUE,
    url VARCHAR(500),
    name VARCHAR(255),
    description TEXT,
    country VARCHAR(10),
    language VARCHAR(10),
    last_verified TIMESTAMP NULL,
    paywall BOOLEAN DEFAULT FALSE,
    paywall_type VARCHAR(50),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Create indexes for sources
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);
CREATE INDEX IF NOT EXISTS idx_sources_country_lang ON sources(country, language);
