# JustNews System Startup Checklist

## Pre-Flight (5 min)

- [ ] Qwen-2.5-14B vLLM running on 8010: `curl -s http://localhost:8010/health`

- [ ] UV/.venv available (or container runtime configured): `test -x .venv/bin/python || echo "using Docker runtime"`

- [ ] Project directory accessible: `cd ${SERVICE_DIR:-$HOME/JustNews} && pwd`

---

## Canonical Startup Checklist (Docker-first)

Follow this sequence for reproducible startup in the canonical Docker runtime:

1. Preflight checks

- [ ] Run: `make docker-preflight`
- [ ] Run compliance check: `make docker-migration-check`

1. One-command startup

- [ ] Run: `make deploy-docker`
  - or `./start_all_services.sh` (wrapper to Docker by default)

1. Service verification

- [ ] Run: `make deploy-docker-status`
- [ ] Check logs: `make deploy-docker-logs`

1. Final health verification

- [ ] Verify key health endpoints from containers/services are healthy
- [ ] Confirm database/vector/cache container health

1. Legacy/systemd note

- [ ] Use systemd app-orchestration only for explicit fallback operations.
- [ ] `start_all_services.sh` and `stop_all_services.sh` are Docker-canonical wrappers.

Notes:

- Use `SAFE_MODE=true` in environment when conservative runtime behavior is required.
- `MARIADB_CHECK_REQUIRED=true` remains recommended for strict startup checks.

---

## Phase 1: Environment Setup (5–30 min)

### 1.1 Global Environment

- [ ] Create `/etc/justnews/global.env`or`./global.env` with:

- `MARIADB_HOST`,`MARIADB_PORT`,`MARIADB_DB`,`MARIADB_USER`,`MARIADB_PASSWORD`

- `CHROMA_HOST`,`CHROMA_PORT`

- `PYTHON_BIN=${SERVICE_DIR:-$HOME/JustNews}/.venv/bin/python` (for non-container local workflows)

- `SERVICE_DIR=${SERVICE_DIR:-$HOME/JustNews}`

- [ ] Test: `source global.env && echo "✅ $MARIADB_HOST"`

### 1.2 MariaDB

- [ ] Start MariaDB:

```bash
  # Option A: Docker
docker compose -f scripts/dev/docker-compose.e2e.yml up -d mariadb

  # Option B: Native (if not running)
sudo ./infrastructure/systemd/setup_mariadb.sh --user justnews_user --password
[password] ```

- [ ] Verify connection: `mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -h $MARIADB_HOST -e "SELECT 1;"`

### 1.3 ChromaDB

- [ ] Start ChromaDB:

```
bash docker run -d --name chromadb -p 8000:8000 chromadb/chroma:latest
```

- [ ] Auto-create articles collection: `python scripts/chroma_diagnose.py --autocreate`

- [ ] Verify: `curl -s <http://localhost:8000/api/v1/heartbeat> | grep -q '{}' && echo "✅"`

---

## Phase 2: Database Schema (5 min)

- [ ] Initialize schema:

```
bash ./scripts/run_with_env.sh python scripts/init_database.py
```Should
print: `✅ Database initialization completed successfully!`

- [ ] Verify tables exist:

```bash mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -D $MARIADB_DB \ -e "SHOW
TABLES;" | grep -c articles
```Should print:`1` (or higher if tables exist)

---

## Phase 3: Agent Services (20–30 min)

### 3.1 MCP Bus

- [ ] Start:

```bash
# Option A: systemd
sudo systemctl enable --now justnews@mcp_bus

# Option B: Direct
./scripts/run_with_env.sh python -m agents.mcp_bus.main &
```

- [ ] Verify: `curl -s <http://localhost:8017/health> && echo "✅ MCP Bus"`

### 3.2 GPU Orchestrator

- [ ] Start:

```bash
# Option A: systemd
sudo systemctl enable --now justnews@gpu_orchestrator

# Option B: Direct
./scripts/run_with_env.sh python -m agents.gpu_orchestrator.main &
```

- [ ] Wait for READY status: `curl -fsS <http://127.0.0.1:8014/ready> && echo "✅ GPU Orchestrator READY"`

### 3.3 Crawler & Crawler Control

- [ ] Start all agents:

```bash
  # Option A: systemd
sudo ./infrastructure/systemd/scripts/enable_all.sh start

  # Option B: Individual services
./scripts/run_with_env.sh python -m agents.crawler.main &
./scripts/run_with_env.sh python -m agents.crawler_control.main &
./scripts/run_with_env.sh python -m agents.analyst.main &
./scripts/run_with_env.sh python -m agents.memory.main & ```

- [ ] Verify health (should all return 200):

```bash for port in 8015 8016 8004 8007; do echo -n "Port $port: " curl -s
<http://localhost:$port/health> | jq -r '.status' done
```

---

## Phase 4: Data Ingestion (20–60 min depending on test size)

### 4.1 Verify Profiles

- [ ] Check profiles exist: `ls -la config/crawl_profiles/`

- [ ] Dry-run scheduler: `./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py --dry-run`

### 4.2 Live Crawl Test

- [ ] Run small test (3 sites × 5 articles):

```bash ./scripts/run_with_env.sh python live_crawl_test.py --sites 3 --articles
5
``` Should fetch ~15 articles and store them

- [ ] Verify articles in database:

```bash mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -D $MARIADB_DB \ -e "SELECT
COUNT(*) AS count FROM articles;"
```

- [ ] Verify ChromaDB embeddings:

```bash curl -s -X POST <http://localhost:8000/api/v1/collections/articles/count>
\ -H "Content-Type: application/json" -d '{}' | jq '.count' ```

### 4.3 Schedule Hourly Crawls (Optional)

- [ ] Dry-run full schedule: `./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py --dry-run`

- [ ] Execute one schedule cycle: `./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py`

- [ ] Setup systemd timer (production):

```bash sudo cp infrastructure/systemd/units/justnews-crawl-scheduler.*
/etc/systemd/system/ sudo systemctl daemon-reload sudo systemctl enable --now justnews-crawl-scheduler.timer
```

---

## Phase 5: Validation & Monitoring

- [ ] Run health check:

```
bash ./infrastructure/systemd/scripts/health_check.sh
```

- [ ] Test full pipeline (optional training data prep):

```bash ./scripts/run_with_env.sh pytest
tests/integration/test_persistence_schema.py -v
```

- [ ] Monitor logs in real-time:

```bash
# MCP Bus
journalctl -u justnews@mcp_bus -f

# Or if running direct Python:
tail -f /var/log/justnews/*.log 2>/dev/null || echo "No logs yet"
```

---

## Success Indicators

✅ **System Ready When All True**:

1. `curl -s <http://localhost:8014/ready`> returns HTTP 200

1. `curl -s <http://localhost:8015/health`> returns 200 (crawler)

1. `curl -s <http://localhost:8016/health`> returns 200 (crawler control)

1. Database articles count > 0

1. ChromaDB collection count > 0

1. No ERROR-level logs in past 5 minutes

✅ **Data Pipeline Working When**:

1. Running crawl produces articles without errors

1. Articles appear in database within 30 seconds

1. Articles get embeddings in ChromaDB

---

## Troubleshooting Quick Fixes

| Symptom | Command to Try | |---------|---| | "MARIADB_HOST: command not found"
| `source global.env`(if using file) or`export MARIADB_HOST=localhost` | |
Port 8015 refused | `curl -s <http://localhost:8014/ready`> – GPU Orchestrator
must be READY first | | ChromaDB not found | `docker ps | grep chromadb` – start
it: `docker run -d --name chromadb -p 8000:8000 chromadb/chroma:latest` | | No
articles after crawl | Check MariaDB: `mysql -u $MARIADB_USER ... -e "SHOW
TABLES;"`– run`init_database.py` if needed | | vLLM 8010 not responding |
`curl -v http://localhost:8010/health` – relaunch:
`./scripts/launch_vllm.sh` |

---

## Time Estimate

| Phase | Est. Time | Notes | |-------|-----------|-------| | Pre-Flight | 2 min
| Verify Docker runtime + vLLM | | Phase 1 (Env + Infra) | 30 min | MariaDB + ChromaDB
setup | | Phase 2 (Schema) | 5 min | Database initialization | | Phase 3
(Agents) | 30 min | MCP + Orchestrator + Crawlers | | Phase 4 (Data) | 20–60 min
| Depends on test size | | **TOTAL** | **~90–120 min** | Full production-ready
system |

---

## Running Checklist Command (Automated)

```bash

## Run this to auto-check most items (requires running agents):

./infrastructure/systemd/scripts/health_check.sh

```

---

**Last Updated**: December 18, 2025
