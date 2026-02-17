-- Migration 018: Add Fact Check Persistence and Source Reliability Metrics
-- Track every fact check performed
CREATE TABLE IF NOT EXISTS fact_checks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fact TEXT NOT NULL,
    verdict ENUM('proven', 'plausible', 'unverified', 'improbable', 'disproven') NOT NULL,
    confidence FLOAT NOT NULL,
    explanation TEXT,
    model_name VARCHAR(255),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Track evidence used for each fact check
CREATE TABLE IF NOT EXISTS fact_check_evidence (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fact_check_id INT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT,
    domain VARCHAR(255),
    credibility_tag VARCHAR(50),
    FOREIGN KEY (fact_check_id) REFERENCES fact_checks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Track Domain Performance
CREATE TABLE IF NOT EXISTS source_reliability_metrics (
    domain VARCHAR(255) PRIMARY KEY,
    proven_count INT DEFAULT 0,    -- Times this source supported a 'proven' result
    disproven_count INT DEFAULT 0, -- Times this source supported a 'disproven' result
    misinfo_count INT DEFAULT 0,   -- Times this source supported a claim that was eventually 'disproven'
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
