-- 012_create_crawler_tables.sql
-- Create tables for web crawler task management and results tracking

-- Crawler tasks table (tracks individual crawl jobs)
CREATE TABLE IF NOT EXISTS crawler_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_id INT,
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    priority INT DEFAULT 0,
    retry_count INT DEFAULT 0,
    error_message TEXT,
    metadata JSON,
    INDEX idx_source_id (source_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Articles discovered per crawler task
CREATE TABLE IF NOT EXISTS crawler_task_articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    crawler_task_id INT NOT NULL,
    article_id INT,
    url VARCHAR(2048),
    title VARCHAR(500),
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_crawler_task_id (crawler_task_id),
    INDEX idx_article_id (article_id),
    FOREIGN KEY (crawler_task_id) REFERENCES crawler_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Crawler crawl results (detailed statistics and results per crawl)
CREATE TABLE IF NOT EXISTS crawler_crawl_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    crawler_task_id INT NOT NULL,
    source_id INT,
    articles_found INT DEFAULT 0,
    articles_new INT DEFAULT 0,
    articles_updated INT DEFAULT 0,
    articles_failed INT DEFAULT 0,
    crawl_duration_seconds INT,
    http_status_code INT,
    error_code VARCHAR(50),
    error_details TEXT,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_crawler_task_id (crawler_task_id),
    INDEX idx_source_id (source_id),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (crawler_task_id) REFERENCES crawler_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at) VALUES ('012_create_crawler_tables', NOW());
