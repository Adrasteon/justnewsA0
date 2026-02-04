# Copilot/AI Assistant Instructions for JustNews System

**Last Updated:** February 3, 2026  
**Purpose:** Provide AI assistants with accurate, complete context to prevent incorrect modifications and enable precise system operations.

---

## CRITICAL SAFETY RULES

⚠️ **Before making ANY changes to this system:**

1. **Always verify you have the complete context** by searching for related files and configurations
2. **Never assume environment structure** - always check current state with `conda env list` or file system queries
3. **Never modify core system files from global.env, environment.yml, or systemd services without explicit instruction**
4. **Always understand the phased environment strategy** before suggesting environment changes
5. **Run `get_errors` or validation checks** after any code changes before confirming completion
6. **Document your reasoning** when making system-level changes

---

## System Architecture Quick Reference

### JustNews Multi-Phase Architecture

The system executes in **4 isolated conda environments**, each optimized for specific workflow phases:

```
PHASE 1 (GPU)           PHASE 2 (CPU)           PHASE 3 (GPU)           PHASE 4 (CPU)
Ingestion &             Clustering &            Synthesis &             Publishing &
Vectorization           Analytics               Curation                Web Stack
├─ crawl4ai             ├─ hdbscan               ├─ vLLM inference        ├─ Django
├─ sentence-trans.      ├─ umap-learn            ├─ LLM synthesis         ├─ Dashboard
├─ PyTorch (CUDA)       ├─ scikit-learn          ├─ Critic agents         ├─ REST API
├─ GPU mode             ├─ CPU-only              ├─ Adaptors (LoRA)       ├─ CPU-only
└─ ~20GB VRAM needed    └─ minimal overhead      └─ ~24GB VRAM needed     └─ lightweight
```

**Critical:** All environments exist and are ready; do NOT rebuild unless explicitly instructed.

### Environment Locations and Details

```bash
# Phase 1: GPU-Enabled Ingestion & Vectorization
Env Name:     justnews-py312-phase1
Path:         /home/adra/miniconda3/envs/justnews-py312-phase1
Config YAML:  /home/adra/justnewsA0/conda/environment.phase1.yml
Python:       /home/adra/miniconda3/envs/justnews-py312-phase1/bin/python
GPU Support:  PyTorch CUDA 12.1, sentence-transformers, crawl4ai
Key Deps:     torch, torchvision, transformers, sentence-transformers, crawl4ai, playwright

# Phase 2: CPU-Only Clustering & Analytics
Env Name:     justnews-py312-phase2
Path:         /home/adra/miniconda3/envs/justnews-py312-phase2
Config YAML:  /home/adra/justnewsA0/conda/environment.phase2.yml
Python:       /home/adra/miniconda3/envs/justnews-py312-phase2/bin/python
GPU Support:  NO - intentionally CPU-only to reduce overhead
Key Deps:     hdbscan, umap-learn, scikit-learn, pandas, networkx

# Phase 3: GPU-Enabled Synthesis & LLM Inference
Env Name:     justnews-py312-phase3
Path:         /home/adra/miniconda3/envs/justnews-py312-phase3
Config YAML:  /home/adra/justnewsA0/conda/environment.phase3.yml
Python:       /home/adra/miniconda3/envs/justnews-py312-phase3/bin/python
GPU Support:  vLLM, PyTorch CUDA, quantization (bitsandbytes)
Key Deps:     vllm, accelerate, bitsandbytes, pytorch, transformers

# Phase 4: CPU-Only Publishing & Django
Env Name:     justnews-py312-phase4
Path:         /home/adra/miniconda3/envs/justnews-py312-phase4
Config YAML:  /home/adra/justnewsA0/conda/environment.phase4.yml
Python:       /home/adra/miniconda3/envs/justnews-py312-phase4/bin/python
GPU Support:  NO - intentionally CPU-only
Key Deps:     django, fastapi, sqlalchemy, mysql-connector-python
```

---

## Global Configuration & Environment Variables

### Primary Configuration Files (Hierarchy)

```
1. /etc/justnews/global.env                 ← System-wide (requires sudo to modify)
2. /home/adra/justnewsA0/global.env         ← Repository local (preferred location)
3. /home/adra/justnewsA0/global.env.sample  ← Template reference
```

**CRITICAL:** Always source from the correct location. The system checks them in this order.

### Essential Global Variables

#### Python & Environment Control

```bash
# Canonical Environment Selection
CANONICAL_ENV=justnews-py312-phase1          # Active phase environment name
PYTHON_BIN=/home/adra/miniconda3/envs/justnews-py312-phase1/bin/python
JUSTNEWS_PYTHON=/home/adra/miniconda3/envs/justnews-py312-phase1/bin/python
ENFORCE_CANONICAL_PYTHON=1                   # 1 = enforce canonical, 0 = allow override

# Conda Configuration
CONDA_PREFIX=/home/adra/miniconda3/envs/justnews-py312-phase1
SERVICE_DIR=/home/adra/justnewsA0
PYTHONPATH=/home/adra/justnewsA0
```

#### Database Configuration (MariaDB)

```bash
MARIADB_HOST=127.0.0.1
MARIADB_PORT=3306
MARIADB_DB=justnews
MARIADB_USER=justnews
MARIADB_PASSWORD=justnews_password          # Stored in Vault; retrieved via scripts/fetch_secrets_to_env.sh
MARIADB_CHARSET=utf8mb4

# Connection Pool Tuning
db_pool_min_connections=2
db_pool_max_connections=10
```

#### ChromaDB Vector Store Configuration

```bash
CHROMADB_HOST=localhost
CHROMADB_PORT=3307                          # Note: NOT the standard 8000
CHROMADB_COLLECTION=articles
CHROMADB_MODEL_SCOPED_COLLECTION=0
CHROMADB_REQUIRE_CANONICAL=1
CHROMADB_CANONICAL_HOST=localhost
CHROMADB_CANONICAL_PORT=3307
```

#### vLLM Inference Server (GPU)

```bash
VLLM_ENABLED=true
VLLM_BASE_URL=http://127.0.0.1:8010/v1
VLLM_API_KEY=unused
VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ   # Quantized model (AWQ Int4)
VLLM_PORT=8010
VLLM_ENABLE_LORA=false                     # Adapter support (disabled by default)
```

#### Crawl4AI Configuration

```bash
CRAWL4AI_HOST=127.0.0.1
CRAWL4AI_PORT=3308
CRAWL4AI_BASE_URL=                         # Optional full URL override
CRAWL4AI_USE_LLM=true                      # Enable LLM extraction
CRAWL4AI_MODEL_CACHE_DIR=/var/lib/justnews/crawl4ai_model_cache
CRAWL4AI_FOLLOW_EXTERNAL=false
```

#### MCP Bus (Multi-Agent Orchestration)

```bash
MCP_BUS_PORT=8000
MCP_BUS_URL=http://localhost:8000           # Derived from port
```

#### Model & Storage Paths

```bash
MODEL_STORE_ROOT=/home/adra/justnewsA0/model_store
BASE_MODEL_DIR=/home/adra/justnewsA0/model_store/base_models
DATA_MOUNT=/media/$(whoami)/Data            # Optional external data mount
```

#### Application Logic Configuration

```bash
CLUSTER_DATERANGE=7                         # Days back for clustering
ENABLE_HITL_PIPELINE=true                   # Human-in-the-loop pipeline
HITL_SERVICE_ADDRESS=http://127.0.0.1:8019
HITL_STATS_INTERVAL_SECONDS=30
HITL_FAILURE_BACKOFF_SECONDS=60
```

#### Monitoring & Observability

```bash
ENABLE_DEV_TELEMETRY=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
JAEGER_ENDPOINT=http://localhost:14268/api/traces
AUTO_INSTALL_ALERTMANAGER=1                # Auto-install Alertmanager on startup
```

#### GPU Runtime Toggles

```bash
BNB_CUDA_VERSION=122                        # Force CUDA 12.2 for bitsandbytes
SAFE_MODE=false                             # Conservative mode for dev hosts
CUDA_VISIBLE_DEVICES=                       # Leave empty = use all; set "0" = first GPU only
```

---

## How to Find & Execute System Functions

### Finding Agent Entry Points

All agents follow the same pattern:

```
agents/
├── crawler/
│   ├── main.py                    ← FastAPI server entry point
│   ├── crawler_engine.py          ← Core crawler logic (class CrawlerEngine)
│   ├── tools.py                   ← Tool definitions for MCP Bus
│   └── job_store.py               ← Job management
├── synthesizer/
│   ├── main.py                    ← LLM synthesis FastAPI server
│   ├── synthesis_engine.py        ← Core synthesis logic
│   └── tools.py                   ← Available tools
├── mcp_bus/
│   ├── main.py                    ← Central orchestration hub
│   ├── mcp_bus_engine.py          ← Engine logic
│   └── tools.py                   ← Tool registry
└── [other agents]/
    ├── main.py
    ├── *_engine.py
    └── tools.py
```

### Running Agent Servers

#### Via Systemd (Production)

```bash
# Start crawler agent (Phase 1 environment)
sudo systemctl start justnews@crawler

# Start synthesizer (Phase 3 environment)
sudo systemctl start justnews@synthesizer

# View logs
sudo journalctl -u justnews@crawler -f
sudo journalctl -u justnews@synthesizer -f
```

#### Via Direct Python (Development)

```bash
# Phase 1 environment
conda activate justnews-py312-phase1
cd /home/adra/justnewsA0
export PYTHONPATH=/home/adra/justnewsA0
python agents/crawler/main.py

# Phase 3 environment (LLM synthesis)
conda activate justnews-py312-phase3
python agents/synthesizer/main.py
```

#### Via Conda Run (Without Activation)

```bash
# Execute in Phase 1 without activation
conda run -n justnews-py312-phase1 python agents/crawler/main.py

# Execute in Phase 3
conda run -n justnews-py312-phase3 python agents/synthesizer/main.py
```

### MCP Bus - Central Tool Registry

The MCP Bus (port 8000) is the central hub for inter-agent communication.

**Location:** `agents/mcp_bus/main.py`

**Query available tools:**
```bash
curl http://localhost:8000/tools
```

**Call a tool via MCP Bus:**
```bash
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "crawler",
    "tool": "unified_production_crawl",
    "kwargs": {
      "domains": ["bbc.com", "cnn.com"],
      "max_articles_per_site": 5,
      "concurrent_sites": 3
    }
  }'
```

### Crawler Agent - Full Crawl Execution

**Location:** `agents/crawler/main.py` (port 8015)

**Launch full crawl (5 articles per site):**
```bash
# Direct HTTP
curl -X POST http://localhost:8015/unified_production_crawl \
  -H "Content-Type: application/json" \
  -d '{
    "name": "unified_production_crawl",
    "args": [],
    "kwargs": {
      "domains": ["domain1.com", "domain2.com", ...],
      "max_articles_per_site": 5,
      "concurrent_sites": 3
    }
  }'

# Response: { "job_id": "abc123...", "status": "accepted" }
```

**Check job status:**
```bash
curl http://localhost:8015/job/{job_id}
```

### Database Functions

**Database module location:** `database/utils/migrated_database_utils.py`

**Common operations:**

```python
from database.utils.migrated_database_utils import create_database_service

# Create connection
db = create_database_service()
db.ensure_conn()
conn = db.get_connection()

# Query sources
cursor = conn.cursor()
cursor.execute("SELECT domain FROM sources")
domains = [r[0] for r in cursor.fetchall()]

# Query article count
cursor.execute("SELECT COUNT(*) FROM articles")
count = cursor.fetchone()[0]

# Close
db.close()
```

### Test Execution (Phased)

**Location:** `scripts/run_phase_tests.sh`

**Run tests for specific phase:**

```bash
# Phase 1 tests (GPU ingestion)
./scripts/run_phase_tests.sh 1 --tb=short

# Phase 2 tests (CPU clustering)
./scripts/run_phase_tests.sh 2 -v

# Phase 3 tests (GPU synthesis/LLM)
./scripts/run_phase_tests.sh 3

# Phase 4 tests (Django/publishing)
./scripts/run_phase_tests.sh 4

# All phases (sequential)
./scripts/run_phase_tests.sh all

# Discover tests without running
./scripts/run_phase_tests.sh all --collect-only
```

### System Startup & Health Checks

**Canonical startup (recommended):**
```bash
sudo ./infrastructure/systemd/canonical_system_startup.sh
# Performs: env validation → migrations → DB checks → service start → smoke tests
```

**Dry-run (safe check):**
```bash
sudo ./infrastructure/systemd/canonical_system_startup.sh --dry-run
```

**Health check:**
```bash
sudo ./infrastructure/systemd/scripts/health_check.sh -v
```

**Stop all services:**
```bash
sudo ./infrastructure/systemd/reset_and_start.sh stop
```

---

## Key File Locations (For Reference & Search)

### Configuration Files

```
/home/adra/justnewsA0/
├── global.env                             ← Active environment variables
├── global.env.sample                      ← Reference template
├── environment.yml                        ← Legacy unified environment (deprecated)
├── Makefile                               ← Build targets (make commands)
├── requirements.txt                       ← Pip requirements (legacy)
├── pytest.ini                             ← Pytest configuration
├── ruff.toml                              ← Linter/formatter config
└── AGENT_MODEL_MAP.json                   ← Agent-to-model mapping
```

### Environment YAML Files (Phased)

```
/home/adra/justnewsA0/conda/
├── environment.base.yml                   ← Shared base (not used directly)
├── environment.phase1.yml                 ← GPU ingestion/vectorization
├── environment.phase2.yml                 ← CPU clustering/analytics
├── environment.phase3.yml                 ← GPU synthesis/LLM
├── environment.phase4.yml                 ← CPU publishing/Django
├── PHASED_ENVIRONMENT_MAPPING.md          ← Phase documentation
└── IMPLEMENTATION_SUMMARY.md              ← Build details
```

### System Infrastructure

```
/home/adra/justnewsA0/infrastructure/systemd/
├── canonical_system_startup.sh            ← Main startup orchestrator
├── preflight.sh                           ← Pre-flight environment checks
├── health_check.sh                        ← Health verification
├── reset_and_start.sh                     ← Service reset & restart
├── cold_start.sh                          ← Cold start sequence
├── vllm.service.example                   ← vLLM systemd template
├── alertmanager.service.example           ← Alertmanager template
├── crawl4ai-bridge.service                ← Crawl4AI service
├── justnews-agent-critic.service          ← Critic agent service
├── justnews-mcp.service                   ← MCP Bus service
├── units/                                 ← Service templates
├── services/                              ← Service scripts
└── mariadb_integration.md                 ← DB setup guide
```

### Scripts

```
/home/adra/justnewsA0/scripts/
├── bootstrap_conda_env.sh                 ← Bootstrap single environment
├── build_phased_envs.sh                   ← Build all 4 phases
├── run_phase_tests.sh                     ← Run tests per phase
├── run_phase1_crawl.sh                    ← Phase 1 crawl test with GPU
├── run_with_env.sh                        ← Run commands with global.env
├── fetch_secrets_to_env.sh                ← Vault integration
├── apply_migrations_script.py              ← Django migrations
├── chroma_bootstrap.py                    ← ChromaDB initialization
└── ci/                                    ← CI/CD scripts
```

### Documentation

```
/home/adra/justnewsA0/docs/
├── INDEX.md                               ← Master documentation index
├── operations/
│   ├── SETUP_GUIDE.md                     ← Installation from scratch
│   ├── STARTUP_CHECKLIST.md               ← Startup verification
│   ├── ENVIRONMENT_CONFIG.md              ← Env variable reference
│   ├── TROUBLESHOOTING.md                 ← Common issues & fixes
│   ├── operator-quick-start.md            ← Daily operations
│   └── MONITORING_INFRASTRUCTURE.md       ← Prometheus/Grafana
├── developer/
│   ├── README.md                          ← Development guidelines
│   └── API_REFERENCE.md                   ← Agent API docs
└── architecture_overview.md               ← System design
```

### Agent Code

```
/home/adra/justnewsA0/agents/
├── crawler/                               ← Web scraping (Phase 1)
│   ├── main.py                            ← FastAPI server
│   ├── crawler_engine.py                  ← Core engine
│   ├── crawler_utils.py                   ← Utilities
│   └── job_store.py                       ← Job persistence
├── synthesizer/                           ← LLM synthesis (Phase 3)
├── memory/                                ← Vector storage & retrieval
├── mcp_bus/                               ← Central orchestration hub
├── common/                                ← Shared utilities
│   ├── mcp_bus_client.py                  ← MCP client
│   └── ...
└── [other agents: journalist, critic, analyst, etc.]
```

### Database

```
/home/adra/justnewsA0/database/
├── utils/
│   └── migrated_database_utils.py         ← Database factory & pooling
├── models.py                              ← SQLAlchemy ORM models
├── core/                                  ← Connection pooling
└── README.md                              ← Schema documentation
```

---

## Context Validation Checklist

Before making changes, verify:

- [ ] **Which phase environment is needed?** (Check CANONICAL_ENV in global.env)
- [ ] **Is the required environment installed?** (Run `conda env list`)
- [ ] **Are all critical services running?** (Check MCP Bus, Crawler, vLLM health)
- [ ] **Is the database connected?** (Test MARIADB_HOST:PORT)
- [ ] **Are global variables sourced correctly?** (Verify /etc/justnews/global.env or local)
- [ ] **Do changes affect systemd services?** (Check `/etc/systemd/system/`)
- [ ] **Will this change break other phases?** (Verify dependency isolation)

---

## Common Mistakes to AVOID

❌ **DON'T:**
- Rebuild environments without explicit instruction (they exist and work)
- Modify global.env without understanding the cascading effects
- Assume one environment can handle all phases (they're intentionally isolated)
- Run GPU code in CPU-only environments (Phase 2/4)
- Skip health checks after system restarts
- Modify systemd service files without reloading with `sudo systemctl daemon-reload`
- Force stop vLLM during model load (wait for /health endpoint)
- Ignore CUDA device allocation (CUDA_VISIBLE_DEVICES controls visibility)

✅ **DO:**
- Always check current state first (conda env list, systemctl status, curl /health)
- Document your understanding of the problem before solving
- Run validation checks after changes (`make lint`, `get_errors`, health checks)
- Use phased test scripts to verify changes in isolation
- Preserve environment isolation - changes in one phase shouldn't affect others
- Check logs after any failure (journalctl, agent logs, error output)
- Follow the canonical startup sequence for fresh system starts

---

## Quick Commands Reference

```bash
# Environment Management
conda env list                              # List all environments
conda activate justnews-py312-phase1        # Activate Phase 1
conda run -n justnews-py312-phase1 python --version  # Run in env

# System Status
curl http://localhost:8000/health           # MCP Bus health
curl http://localhost:8015/health           # Crawler health
curl http://localhost:8010/health           # vLLM health
sudo systemctl status justnews@mcp_bus      # Service status

# Database
python -c "from database.utils.migrated_database_utils import create_database_service; \
db = create_database_service(); db.ensure_conn(); print('✅ DB Connected')"

# Configuration
source /home/adra/justnewsA0/global.env    # Load global env
echo $CANONICAL_ENV                         # Check active env
echo $VLLM_MODEL                            # Check model

# Logging
sudo journalctl -u justnews@crawler -f      # Tail crawler logs
sudo journalctl -u justnews@mcp_bus -f      # Tail MCP Bus logs
tail -n 100 /home/adra/justnewsA0/run/gpu_monitor.log  # GPU monitor

# Testing
./scripts/run_phase_tests.sh 1 -v           # Phase 1 tests verbose
./scripts/run_phase_tests.sh all --collect-only  # Discover all tests

# Startup/Shutdown
sudo ./infrastructure/systemd/canonical_system_startup.sh      # Full startup
sudo ./infrastructure/systemd/canonical_system_startup.sh --dry-run  # Check only
sudo ./infrastructure/systemd/reset_and_start.sh stop         # Stop all services
```

---

## When to Ask for Help

Contact a system administrator if:
- A phased environment needs rebuilding (don't attempt without guidance)
- vLLM fails to load the model (GPU memory or CUDA issues)
- Database connectivity fails (MariaDB/ChromaDB connection problems)
- Systemd services won't start (permission or path issues)
- You need to modify `/etc/justnews/global.env` (requires sudo)
- Unsure about environment isolation impacts

---

**This document is the source of truth for AI assistants working on this system. Refer to it before making any decisions.**
