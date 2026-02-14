--- title: Environment and Configuration Guide description: Complete guide to JustNews environment setup, global.env,
and configuration management ---

# Environment and Configuration Guide

This document covers environment configuration, the global.env file, and how the system integrates with Vault for
secrets management.

## Overview

JustNews uses a **layered configuration approach**:

1. **Global Defaults** (`/etc/justnews/global.env`or`./global.env`)

1. **Secrets** (`/run/justnews/secrets.env`, sourced from Vault)

1. **Local Overrides** (`./secrets.env`, for development)

1. **Runtime Variables** (exported directly)

The `scripts/run_with_env.sh` wrapper sources these in order, so later values override earlier ones.

## The `/etc/justnews/global.env` File

### Purpose

System-wide, non-secret configuration defaults for all JustNews services.

### Location

- **System**: `/etc/justnews/global.env` (managed by operators)

- **Repo**: `./global.env` (fallback for dev; fallback if system file missing)

### Key Sections

#### Python & Environment

```bash

## Canonical environment name

CANONICAL_ENV=${CANONICAL_ENV:-justnews-py312-phase1}

## Paths to Python interpreter (must match conda environment)

PYTHON_BIN=$HOME/miniconda3/envs/${CANONICAL_ENV:-justnews-py312-phase1}/bin/python
JUSTNEWS_PYTHON=$PYTHON_BIN
CANONICAL_PYTHON_PATH=$PYTHON_BIN

## Enforce Python path on startup (0 = off, 1 = enforce)

ENFORCE_CANONICAL_PYTHON=1

## Service directory

SERVICE_DIR=${SERVICE_DIR:-$HOME/JustNews}
PYTHONPATH=${SERVICE_DIR:-$HOME/JustNews}

## Conda prefix

CONDA_PREFIX=$HOME/miniconda3/envs/${CANONICAL_ENV:-justnews-py312-phase1}

```

#### Data Storage

```bash

## Model store root (for downloaded LLMs, embeddings)

MODEL_STORE_ROOT=${SERVICE_DIR:-$HOME/JustNews}/model_store

## Agent model cache

BASE_MODEL_DIR=${SERVICE_DIR:-$HOME/JustNews}/model_store/base_models

## Data mount (should be spacious, 100+ GB for models)

DATA_MOUNT=/media/adra/Data

```

#### Database Configuration

```bash

## MariaDB connection

MARIADB_HOST=127.0.0.1
MARIADB_PORT=3306
MARIADB_DB=justnews
MARIADB_USER=justnews
MARIADB_PASSWORD=<from-vault>  # NOT stored in global.env; injected at runtime

## Connection pool tuning

db_pool_min_connections=2
db_pool_max_connections=10
MARIADB_CHARSET=utf8mb4

```bash

#### Vector Database (ChromaDB)

```bash

## Runtime ChromaDB location

CHROMADB_HOST=localhost
CHROMADB_PORT=3307
CHROMADB_COLLECTION=articles

## Canonical enforcement (ensures all agents use same instance)

CHROMADB_REQUIRE_CANONICAL=1
CHROMADB_CANONICAL_HOST=localhost
CHROMADB_CANONICAL_PORT=3307

```

#### Human-in-the-Loop (HITL)

```bash
ENABLE_HITL_PIPELINE=true
HITL_SERVICE_ADDRESS=http://127.0.0.1:8040
HITL_STATS_INTERVAL_SECONDS=30
HITL_FAILURE_BACKOFF_SECONDS=60
HITL_FORWARD_AGENT=archive
HITL_FORWARD_TOOL=queue_article

```

#### Service Ports

```bash

## MCP Bus (central message broker)

MCP_BUS_HOST=localhost
MCP_BUS_PORT=8000
MCP_BUS_MISSING_AGENT_POLL_INTERVAL_SEC=30

## Unified Crawler

UNIFIED_CRAWLER_ENABLE_HTTP_FETCH=true
UNIFIED_CRAWLER_DEDUPE_REPLACEMENT_FACTOR=3
UNIFIED_CRAWLER_MAX_REQUEST_CAP=150

## Analytics Dashboard

ANALYTICS_AGENT_PORT=8012

## Fact Checker Shim

FACT_CHECKER_AGENT_PORT=8018
FACT_CHECKER_EXTERNAL_URL=http://localhost:8003

## Transparency/Evidence Service

EVIDENCE_AUDIT_BASE_URL=http://localhost:8013/transparency

```

Crawler dedupe replacement tuning notes:

- `UNIFIED_CRAWLER_DEDUPE_REPLACEMENT_FACTOR`
	- Multiplies candidate fetch size per batch to compensate when ingest dedupe skips candidates.
	- Higher values improve chance of hitting requested **new-article** targets but increase crawl cost.
- `UNIFIED_CRAWLER_MAX_REQUEST_CAP`
	- Hard cap for per-batch candidate request size.
	- Protects against runaway fetches on high-duplication domains.

Recommended starting point (development):

- `UNIFIED_CRAWLER_DEDUPE_REPLACEMENT_FACTOR=3`
- `UNIFIED_CRAWLER_MAX_REQUEST_CAP=150`

#### Telemetry & Monitoring

```bash

## OpenTelemetry

OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true

## Tracing

ENABLE_TRACING=1

```

## Secrets Management

### Secret Sources (in priority order)

The wrapper script (`run_with_env.sh`) sources:

1. **System global.env**: `/etc/justnews/global.env`

1. **Repo fallback**: `./global.env`

1. **Runtime secrets**: `/run/justnews/secrets.env` (from Vault)

1. **System secrets**: `/etc/justnews/secrets.env` (local override)

1. **Repo secrets**: `./secrets.env` (development, gitignored)

### Secrets Currently Managed by Vault

```

MARIADB_PASSWORD          -- Database user password
PIA_SOCKS5_HOST          -- Proxy server hostname
PIA_SOCKS5_PORT          -- Proxy server port
PIA_SOCKS5_USER          -- Proxy authentication username
PIA_SOCKS5_PASS          -- Proxy authentication password
ADMIN_API_KEY            -- Admin panel API key

```

### Fetching Secrets

```bash

## Manually fetch from Vault

bash scripts/fetch_secrets_to_env.sh

## Creates: /run/justnews/secrets.env (mode 0640, ephemeral)

## This file is sourced by run_with_env.sh at runtime

```

### Using with Commands

```bash

## All secrets available to the command

bash scripts/run_with_env.sh python check_databases.py

## Verify secrets are loaded

bash scripts/run_with_env.sh env | grep "MARIADB_PASSWORD"

```bash

## Configuration Loading in Code

### Python applications should use:

```python
from common.env_loader import load_global_env

## Load environment (respects JUSTNEWS_GLOBAL_ENV override)

logger = load_global_env(logger=logger)

## Now environment variables are available

import os
db_password = os.environ.get('MARIADB_PASSWORD')

```

### The env_loader respects:

- `JUSTNEWS_GLOBAL_ENV` — override path to global.env

- System config at `/etc/justnews/global.env` (preferred)

- Fallback to `./global.env` in repo

## Directory Structure

```bash

/etc/justnews/              (system config, requires sudo)
├── global.env              (non-secret defaults)
├── approle_role_id         (AppRole role ID, mode 0640)
├── approle_secret_id       (AppRole secret ID, mode 0640)
├── vault_role_id           (symlink)
├── vault_secret_id         (symlink)
└── vault-init.json         (init credentials, mode 0600)

/run/justnews/              (runtime, ephemeral tmpfs)
└── secrets.env             (Vault-fetched secrets, mode 0640)

./JustNews/                 (repository)
├── global.env              (repo defaults, fallback)
└── secrets.env             (optional dev override, .gitignored)

```

## Service Configuration Integration

### Systemd Services

Services can source the environment via `EnvironmentFile`:

```ini
[Service]
EnvironmentFile=/etc/justnews/global.env
ExecStartPre=/bin/bash -c 'bash scripts/fetch_secrets_to_env.sh'
ExecStart=/bin/bash scripts/run_with_env.sh /path/to/app

```bash

### Agent Startup

```bash

## Start an agent with full environment

sudo systemctl start justnews@scout

## Verify environment

sudo systemctl cat justnews@scout | grep Environment

```

## Common Environment Variables

| Variable | Purpose | Example | |----------|---------|---------| | `CANONICAL_ENV` | Conda environment name |
`justnews-py312`| |`PYTHON_BIN`| Path to Python interpreter |`/home/adra/miniconda3/envs/justnews- py312/bin/python`
| | `PYTHONPATH`| Python import path |`/home/adra/JustNews`| |`MARIADB_HOST`| Database host |`127.0.0.1` | |
`MARIADB_PORT`| Database port |`3306`| |`CHROMADB_HOST`| Vector DB host |`localhost`| |`CHROMADB_PORT` | Vector
DB port | `3307`| |`MODEL_STORE_ROOT`| LLM storage path |`/home/adra/JustNews/model_store`| |`DATA_MOUNT` | Data
directory | `/media/adra/Data` |

## Troubleshooting

### Environment Variables Not Found

```bash

## Check which global.env is being loaded

bash scripts/run_with_env.sh env | grep "MARIADB_HOST"

## Verify file exists

ls -lh /etc/justnews/global.env ./global.env

## Debug wrapper script

bash -x scripts/run_with_env.sh echo "test"

```bash

### Secrets Not Available

```bash

## Fetch from Vault

bash scripts/fetch_secrets_to_env.sh

## Verify file created

sudo ls -lh /run/justnews/secrets.env
sudo cat /run/justnews/secrets.env

## Check permissions

sudo ls -lh /etc/justnews/approle_*

```

### Wrong Python Interpreter

```bash

## Verify PYTHON_BIN setting

bash scripts/run_with_env.sh which python

## Should match CANONICAL_PYTHON_PATH

which python  # Compare

## If mismatch, update /etc/justnews/global.env

```

## Next Steps

1. **Operators**: See `docs/operations/SETUP_GUIDE.md` for complete systemd deployment

1. **Developers**: See `docs/developer/` for development environment setup

1. **Secrets**: See `docs/operations/VAULT_SETUP.md` for Vault administration
