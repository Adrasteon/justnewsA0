-- 013_create_publisher_tables.sql
-- Create tables for the Publisher frontend (news website)

-- Publisher sources (curated list of sources displayed on the website)
CREATE TABLE IF NOT EXISTS publisher_sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_id INT UNIQUE,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    description TEXT,
    category VARCHAR(100),
    is_featured BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    icon_url VARCHAR(2048),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_is_active (is_active),
    INDEX idx_is_featured (is_featured),
    INDEX idx_category (category),
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Publisher articles (articles displayed on the website)
CREATE TABLE IF NOT EXISTS publisher_articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    article_id INT UNIQUE,
    publisher_source_id INT,
    title VARCHAR(500),
    summary TEXT,
    content TEXT,
    featured_image_url VARCHAR(2048),
    is_featured BOOLEAN DEFAULT FALSE,
    is_published BOOLEAN DEFAULT FALSE,
    view_count INT DEFAULT 0,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_is_published (is_published),
    INDEX idx_is_featured (is_featured),
    INDEX idx_published_at (published_at),
    INDEX idx_publisher_source_id (publisher_source_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (publisher_source_id) REFERENCES publisher_sources(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Publisher keywords/tags (for content categorization and search)
CREATE TABLE IF NOT EXISTS publisher_keywords (
    id INT AUTO_INCREMENT PRIMARY KEY,
    publisher_article_id INT,
    keyword VARCHAR(100) NOT NULL,
    confidence DECIMAL(5, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_publisher_article_id (publisher_article_id),
    INDEX idx_keyword (keyword),
    FOREIGN KEY (publisher_article_id) REFERENCES publisher_articles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at) VALUES ('013_create_publisher_tables', NOW());
