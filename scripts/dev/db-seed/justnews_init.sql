-- DB seed for JustNews E2E PoC
-- Creates test database, user and minimal schema used by E2E tests.

CREATE DATABASE IF NOT EXISTS justnews_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'justnews'@'%' IDENTIFIED BY 'test';
GRANT ALL PRIVILEGES ON justnews_test.* TO 'justnews'@'%';
FLUSH PRIVILEGES;

USE justnews_test;

-- orchestrator_leases
CREATE TABLE IF NOT EXISTS orchestrator_leases (
  token VARCHAR(64) PRIMARY KEY,
  agent_name VARCHAR(255) NOT NULL,
  gpu_index INT NULL,
  mode VARCHAR(16) NOT NULL DEFAULT 'gpu',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NULL,
  last_heartbeat TIMESTAMP NULL,
  metadata JSON NULL
) ENGINE=InnoDB;

-- worker_pools
CREATE TABLE IF NOT EXISTS worker_pools (
  pool_id VARCHAR(128) PRIMARY KEY,
  agent_name VARCHAR(255) NULL,
  model_id VARCHAR(255) NULL,
  adapter VARCHAR(255) NULL,
  desired_workers INT NOT NULL DEFAULT 0,
  spawned_workers INT NOT NULL DEFAULT 0,
  started_at TIMESTAMP NULL,
  last_heartbeat TIMESTAMP NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'starting',
  hold_seconds INT NOT NULL DEFAULT 600,
  metadata JSON NULL
) ENGINE=InnoDB;

-- orchestrator_jobs
CREATE TABLE IF NOT EXISTS orchestrator_jobs (
  job_id VARCHAR(128) PRIMARY KEY,
  type VARCHAR(64) NOT NULL,
  payload JSON NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  owner_pool VARCHAR(128) NULL,
  attempts INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NULL,
  last_error TEXT NULL
) ENGINE=InnoDB;

-- crawler_jobs
CREATE TABLE IF NOT EXISTS crawler_jobs (
  job_id VARCHAR(64) PRIMARY KEY,
  status VARCHAR(32) NOT NULL,
  result TEXT NULL,
  error TEXT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Seed sample data used by lightweight E2E smoke/representative tests
INSERT INTO orchestrator_leases (token, agent_name, gpu_index, mode, created_at, expires_at, last_heartbeat, metadata)
VALUES ('seed-lease-1', 'test-agent', 0, 'gpu', NOW(), NULL, NOW(), JSON_OBJECT('note', 'seeded'))
ON DUPLICATE KEY UPDATE token=token;

INSERT INTO worker_pools (pool_id, agent_name, model_id, adapter, desired_workers, spawned_workers, started_at, last_heartbeat, status, hold_seconds, metadata)
VALUES ('seed-pool-1', 'test-agent', 'test-model', 'test-adapter', 1, 0, NOW(), NOW(), 'running', 600, JSON_OBJECT('note', 'seeded'))
ON DUPLICATE KEY UPDATE pool_id=pool_id;

INSERT INTO orchestrator_jobs (job_id, type, payload, status, owner_pool, attempts, created_at)
VALUES ('seed-job-1', 'inference', '{"text": "smoke test"}', 'pending', 'seed-pool-1', 0, NOW())
ON DUPLICATE KEY UPDATE job_id=job_id;
