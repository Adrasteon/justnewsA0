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

## Dependency manifests (UV/Pip canonical)

- `requirements-bootstrap.txt` is the canonical UV/.venv bootstrap dependency manifest.
- `requirements.txt` is a compatibility wrapper that includes `requirements-bootstrap.txt`.
- Legacy conda manifests are deprecated and moved to local archive references only.

Recommended:

- Use UV/venv for primary runtime provisioning.
- Do not use conda/mamba for active setup, CI, or runtime flows.
- Keep `requirements-bootstrap.txt` aligned with runtime requirements used by `.venv`.

### Decision note (2026-03-22): Docker builds remain pip-based

For clarity and operational stability, Docker image builds remain on `pip install -r requirements.txt` for now.

Rationale:

- Existing Dockerfiles across services are consistently pip-based.
- The current priority is system stability and output accuracy, not dependency-tool migration risk.
- UV migration for Docker remains a planned future improvement once the platform is more stable.

Fact-checker model loading alignment (2026-03-22):

- Build-time Hugging Face pre-download was removed from the fact-checker image.
- Fact-checker embedding initialization now prefers central model-store paths when `MODEL_STORE_ROOT` is set.
- Optional controls for strictness and path pinning:
	- `STRICT_MODEL_STORE=1` to fail fast when model-store resolution is required but unavailable.
	- `MODEL_STORE_EMBEDDING_AGENT` to select model-store namespace (default: `fact_checker`).
	- `MODEL_STORE_EMBEDDING_PATH` (relative under model store) or `EMBEDDING_MODEL_PATH` (absolute path) for explicit targeting.

Fact-checker strict-mode bootstrap (pre-start):

```bash
mkdir -p model_store
MODEL_STORE_ROOT=$PWD/model_store \
	/app/.venv/bin/python scripts/publish_hf_to_model_store.py \
	--agent fact_checker \
	--model BAAI/bge-large-en-v1.5 \
	--version v_fact_checker_embedding_bge_large_en_v1_5
```

Model-store root note (devcontainer vs canonical host):

- In this workspace/devcontainer flow, fact-checker currently uses a workspace-scoped model store root (`/app/model_store`) mounted from the repository.
- In canonical host deployments, `MODEL_STORE_ROOT` is typically a host-global path (for example `${SERVICE_DIR}/model_store`).
- This is the same model-store system and layout, but with a different root path scope.

Recommendation for strict consistency later:

- Standardize a single `MODEL_STORE_ROOT` convention per environment tier (dev, staging, prod) and apply it uniformly across all agents/services.
- Add a pre-start validation check that fails startup if `STRICT_MODEL_STORE=1` and required model-store payloads are missing.
- Use `MODEL_STORE_EMBEDDING_PATH` for deterministic path pinning when reproducibility is required across rollouts.
- Keep environment documentation and compose/systemd manifests aligned whenever root paths change.

Related context: the current non-checklist working-tree changes are documented in `docs/operations/HYBRID_WHITELIST_DISCOVERY_EXECUTION_CHECKLIST_2026-03-21.md` under "Repository Working Tree Context (2026-03-22)".

## The `/etc/justnews/global.env` File

### Purpose

System-wide, non-secret configuration defaults for all JustNews services.

### Location

- **System**: `/etc/justnews/global.env` (managed by operators)

- **Repo**: `./global.env` (fallback for dev; fallback if system file missing)

### Key Sections

#### Python & Environment

```bash

## Canonical Python runtime (UV/venv)

VENV_DIR=${VENV_DIR:-${SERVICE_DIR:-$HOME/JustNews}/.venv}
PYTHON_BIN=${PYTHON_BIN:-${VENV_DIR}/bin/python}
JUSTNEWS_PYTHON=${JUSTNEWS_PYTHON:-$PYTHON_BIN}
CANONICAL_PYTHON_PATH=${CANONICAL_PYTHON_PATH:-$PYTHON_BIN}

## Enforce Python path on startup (0 = off, 1 = enforce)

ENFORCE_CANONICAL_PYTHON=1

## Service directory

SERVICE_DIR=${SERVICE_DIR:-$HOME/JustNews}
PYTHONPATH=${SERVICE_DIR:-$HOME/JustNews}

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
UNIFIED_CRAWLER_INGEST_MAX_INFLIGHT=6
UNIFIED_CRAWLER_INGEST_BACKOFF_SECONDS=8
UNIFIED_CRAWLER_INGEST_SPOOL_ENABLED=true
UNIFIED_CRAWLER_INGEST_SPOOL_DIR=/var/lib/justnews/spool/crawler_ingest
UNIFIED_CRAWLER_INGEST_SPOOL_MAX_ITEMS=2500
UNIFIED_CRAWLER_INGEST_SPOOL_REPLAY_BATCH=25

## Analytics Dashboard

ANALYTICS_AGENT_PORT=8012

## Fact Checker Shim

FACT_CHECKER_AGENT_PORT=8018
FACT_CHECKER_EXTERNAL_URL=http://fact-checker:8000
FACT_CHECKER_API_KEY=dev_key_123
FACT_CHECKER_SHIM_TIMEOUT_SEC=45
FACT_CHECKER_SHIM_MAX_RETRIES=0
FACT_CHECKER_SHIM_CB_FAILURE_THRESHOLD=20
FACT_CHECKER_SHIM_CB_OPEN_SEC=20

## Memory load-shedding (optional under sustained ingest pressure)

MEMORY_ESSENTIAL_MODE=true

## Startup RAM guardrail (host memory pressure protection)

JUSTNEWS_RAM_CAP_ENFORCE=1
JUSTNEWS_RAM_CAP_PERCENT=85
JUSTNEWS_RAM_CAP_WAIT_SECONDS=120
JUSTNEWS_RAM_CAP_CHECK_INTERVAL_SECONDS=5

## Runtime memory governor (portable lifecycle control)

JUSTNEWS_MEMORY_GOVERNOR_ENABLED=1
JUSTNEWS_MEMORY_SOFT_PERCENT=85
JUSTNEWS_MEMORY_HARD_PERCENT=88
JUSTNEWS_MEMORY_EMERGENCY_PERCENT=92
JUSTNEWS_MEMORY_RESUME_PERCENT=80
JUSTNEWS_MEMORY_CHECK_INTERVAL_SECONDS=5
JUSTNEWS_MEMORY_ACTION_COOLDOWN_SECONDS=20
JUSTNEWS_MEMORY_TERMINATE_GRACE_SECONDS=12

## Training system forwarding controls

TRAINING_SYSTEM_URL=http://localhost:8011
TRAINING_SYSTEM_FORWARD_ENABLED=1
TRAINING_SYSTEM_FORWARD_TIMEOUT_SEC=8.0
TRAINING_SYSTEM_LOCAL_FALLBACK_ENABLED=0

## Workflow autonomic controller

AUTONOMIC_MODE=shadow
AUTONOMIC_DECISIONS_ENABLED=1
AUTONOMIC_LEARNING_ENABLED=1

## Workflow Orchestrator (validated low-load profile)

MAX_CONCURRENT_TASKS=20

## Transparency/Evidence Service

EVIDENCE_AUDIT_BASE_URL=http://localhost:8013/transparency

```

#### Chief Editor (Qwen Runtime)

```bash

## Shared vLLM endpoint/model used by Chief Editor adapter

VLLM_BASE_URL=http://127.0.0.1:8010/v1
VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ
VLLM_API_KEY=unused

## Chief Editor runtime toggle (Qwen-only path)

CHIEF_EDITOR_DISABLE_QWEN=0

```

Notes:

- Chief Editor uses the Qwen adapter path for quality, categorization, sentiment, and commentary.
- Legacy `CHIEF_EDITOR_DISABLE_MISTRAL` compatibility behavior is removed; use `CHIEF_EDITOR_DISABLE_QWEN` only.

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

Crawler ingest resiliency notes:

- `UNIFIED_CRAWLER_INGEST_SPOOL_ENABLED`
	- Enables disk-backed deferred ingest queueing when memory/bus is transiently unavailable.
- `UNIFIED_CRAWLER_INGEST_SPOOL_DIR`
	- Use a persistent volume-backed path for durability across restarts/reboots.
- `UNIFIED_CRAWLER_INGEST_SPOOL_MAX_ITEMS`
	- Hard cap on deferred entries; oldest entries are pruned first when exceeded.
- `UNIFIED_CRAWLER_INGEST_SPOOL_REPLAY_BATCH`
	- Max spooled entries replayed per ingest cycle.
- `UNIFIED_CRAWLER_INGEST_MAX_INFLIGHT` / `UNIFIED_CRAWLER_INGEST_BACKOFF_SECONDS`
	- Primary controls for route pressure and retry pacing.

Memory pressure mitigation note:

- `MEMORY_ESSENTIAL_MODE=true` keeps core ingest path prioritized by skipping optional heavy post-ingest work.

Startup RAM guardrail notes:

- `JUSTNEWS_RAM_CAP_ENFORCE=1`
	- Enables host RAM gate in `start_all_services.sh` before each agent/publisher launch.
- `JUSTNEWS_RAM_CAP_PERCENT`
	- Blocks additional service startup while host RAM usage is at/above this threshold (use `85` to reserve ~15% headroom).
- `JUSTNEWS_RAM_CAP_WAIT_SECONDS` and `JUSTNEWS_RAM_CAP_CHECK_INTERVAL_SECONDS`
	- Control how long startup waits for memory pressure to subside before aborting.

Runtime memory governor notes:

- `JUSTNEWS_MEMORY_GOVERNOR_ENABLED=1`
	- Starts `scripts/ops/justnews_memory_governor.py` after startup completes.
- `JUSTNEWS_MEMORY_SOFT_PERCENT` / `JUSTNEWS_MEMORY_HARD_PERCENT` / `JUSTNEWS_MEMORY_EMERGENCY_PERCENT`
	- Tiered lifecycle controls to reduce pressure without immediate hard kills.
- `JUSTNEWS_MEMORY_RESUME_PERCENT`
	- Hysteresis threshold used to resume paused non-critical services once pressure drops.
- `JUSTNEWS_MEMORY_ACTION_COOLDOWN_SECONDS`
	- Prevents action thrashing under noisy memory usage.
- `JUSTNEWS_MEMORY_TERMINATE_GRACE_SECONDS`
	- Graceful termination window before forced kill when shedding process memory.

Workflow autonomic controller notes:

- `AUTONOMIC_MODE`
	- `disabled` disables decisions entirely, `shadow` records decisions without applying changes, `active` can apply bounded runtime patches.
- `AUTONOMIC_DECISIONS_ENABLED`
	- Feature flag for running the decision cycle.
- `AUTONOMIC_LEARNING_ENABLED`
	- Enables shadow-mode learning telemetry collection.

Runtime diagnostics:

- Endpoint: `GET /autonomic/status` on `workflow_orchestrator` (port `8023`).
- In shadow mode, `last_decision` is now populated early per tick and shadow decisions are logged as:
	- `Autonomic shadow decision recorded: status=<...> reason=<...> patch=<...>`

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
