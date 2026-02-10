-- 014_create_embeddings_tables.sql
-- Create tables for managing embeddings in the ChromaDB system

-- Embeddings collection metadata (tracks collections in ChromaDB)
CREATE TABLE IF NOT EXISTS embeddings_collection (
    id INT AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    model_name VARCHAR(255),
    embedding_dimension INT,
    document_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    metadata JSON,
    INDEX idx_collection_name (collection_name),
    INDEX idx_model_name (model_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Embeddings documents (individual documents with their embeddings)
CREATE TABLE IF NOT EXISTS embeddings_document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    embeddings_collection_id INT NOT NULL,
    document_id VARCHAR(255) NOT NULL,
    content TEXT,
    content_hash VARCHAR(64),
    embedding_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP NULL,
    metadata JSON,
    UNIQUE KEY unique_collection_document (embeddings_collection_id, document_id),
    INDEX idx_collection_id (embeddings_collection_id),
    INDEX idx_document_id (document_id),
    INDEX idx_status (embedding_status),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (embeddings_collection_id) REFERENCES embeddings_collection(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at) VALUES ('014_create_embeddings_tables', NOW());
