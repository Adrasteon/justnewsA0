# Quick Reference Card

Print this page or keep it open while executing the startup plan.

---

## Phase 1: Environment Setup (5-30 min)

### 1.1 Create global.env

```bash

## Create /etc/justnews/global.env or ./global.env with:

JUSTNEWS_PYTHON=/home/adra/miniconda3/envs/${CANONICAL_ENV:-justnews-py312}/bin/python
SERVICE_DIR=/home/adra/JustNews
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_DB=justnews
MARIADB_USER=justnews_user
MARIADB_PASSWORD=<strong-password>
CHROMA_HOST=localhost
CHROMA_PORT=8000
CANONICAL_ENV=justnews-py312

## Verify:

source global.env && echo "✅ $MARIADB_HOST"

```bash

### 1.2 Start MariaDB

```bash

## Docker (simplest)

docker-compose -f scripts/dev/docker-compose.e2e.yml up -d mariadb

## Or verify if running:

mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -h $MARIADB_HOST -e "SELECT 1;"

```

### 1.3 Start ChromaDB

```bash

## Docker

docker run -d --name chromadb -p 8000:8000 chromadb/chroma:latest

## Auto-create collection

python scripts/chroma_diagnose.py --autocreate

```bash

---

**User/Dev One-Page Startup Guide:** `infrastructure/systemd/USER_DEV_SYSTEM_START_GUIDE.md` — a printable, concise
checklist for starting and verifying JustNews (recommended).

## Phase 2: Database Schema (5 min)

```bash

## Initialize schema

./scripts/run_with_env.sh python scripts/init_database.py

## Should output: ✅ Database initialization completed successfully!

## Verify

mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -D $MARIADB_DB \
  -e "SHOW TABLES;" | grep -c articles

```

---

## Phase 3: Agent Services (20-30 min)

### 3.0 Start Observability (Optional)

Start the OpenTelemetry collector to capture traces locally:

```bash
./scripts/ops/run_local_otel.sh &
```

### 3.1 MCP Bus

```bash

## Option A: systemd

sudo systemctl enable --now justnews@mcp_bus

## Option B: Direct Python

./scripts/run_with_env.sh python -m agents.mcp_bus.main &

## Verify

curl -s <http://localhost:8017/health> && echo "✅ MCP Bus"

```bash

### 3.2 GPU Orchestrator (WAIT for READY)

```bash

## Option A: systemd

sudo systemctl enable --now justnews@gpu_orchestrator

## Option B: Direct Python

./scripts/run_with_env.sh python -m agents.gpu_orchestrator.main &

## WAIT for ready (try every 5 seconds):

for i in {1..30}; do
  curl -fsS <http://127.0.0.1:8014/ready> && echo "✅ GPU Orchestrator READY" && break
  sleep 5
done

```

### 3.3 Crawler Agents

```bash

## Option A: systemd (all services)

sudo ./infrastructure/systemd/scripts/enable_all.sh start

## Option B: Individual services

./scripts/run_with_env.sh python -m agents.crawler.main &
./scripts/run_with_env.sh python -m agents.crawler_control.main &
./scripts/run_with_env.sh python -m agents.analyst.main &
./scripts/run_with_env.sh python -m agents.memory.main &

## Verify all ports

for port in 8015 8016 8004 8007; do
  echo -n "Port $port: "
  curl -s <http://localhost:$port/health> | jq -r '.status'
done

```bash

---

## Phase 4: Data Ingestion (20-60 min)

### 4.1 Verify Profiles

```bash
ls -la config/crawl_profiles/
./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py --dry-run

```

### 4.2 Small Crawl Test (15 articles)

```bash
./scripts/run_with_env.sh python live_crawl_test.py --sites 3 --articles 5

```bash

### 4.3 Check Results

```bash

## Articles in database

mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -D $MARIADB_DB \
  -e "SELECT COUNT(*) AS count FROM articles;"

## Embeddings in ChromaDB

curl -s -X POST <http://localhost:8000/api/v1/collections/articles/count> \
  -H "Content-Type: application/json" -d '{}' | jq '.count'

```

### 4.4 Full Scheduler (500 articles/hour)

```bash

## Dry-run first

./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py --dry-run

## Execute one cycle

./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py

```bash

---

## Health Check (Copy-Paste)

```bash

## Quick health check of all services

echo "MCP Bus:"
curl -s <http://localhost:8017/health> | jq '.status'

echo "GPU Orchestrator:"
curl -fsS <http://127.0.0.1:8014/ready> && echo "READY" || echo "NOT READY"

echo "Crawler:"
curl -s <http://localhost:8015/health> | jq '.status'

echo "Crawler Control:"
curl -s <http://localhost:8016/health> | jq '.status'

echo "Analyst:"
curl -s <http://localhost:8004/health> | jq '.status'

echo "Memory:"
curl -s <http://localhost:8007/health> | jq '.status'

echo "MariaDB:"
mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -h $MARIADB_HOST \
  -e "SELECT COUNT(*) AS articles FROM articles;" 2>/dev/null || echo "NOT CONNECTED"

echo "ChromaDB:"
curl -s <http://localhost:8000/api/v1/heartbeat> | grep -q '{}' && echo "OK" || echo "NOT RESPONDING"

```

---

## Troubleshooting

| Symptom | Check | Fix | |---------|-------|-----| | "command not found: source" | Global env | Use
`./scripts/run_with_env.sh`or run`export MARIADB_HOST=localhost` | | Port 8015 refused | GPU Orchestrator ready? |
`curl -fsS <http://127.0.0.1:8014/ready`> – wait until 200 | | No ChromaDB at 8000 | Docker running? |`docker ps | grep
chromadb` – if missing, run Docker start command | | Articles count = 0 | Database schema? | Run
`scripts/init_database.py`again | | MariaDB won't connect | Password correct? | Check`MARIADB_PASSWORD` in global.env
| | vLLM 7060 crashed | Check logs | `tail -50 /home/adra/JustNews/run/vllm_mistral_fp16.log` |

---

## Port Map

| Service | Port | Health Check | |---------|------|--------------| | MCP Bus | 8017 | `curl
<http://localhost:8017/health`> | | GPU Orchestrator | 8014 |`curl <http://localhost:8014/ready`> | | Crawler | 8015 |
`curl <http://localhost:8015/health`> | | Crawler Control | 8016 |`curl <http://localhost:8016/health`> | | Analyst | 8004
| `curl <http://localhost:8004/health`> | | Memory | 8007 |`curl <http://localhost:8007/health`> | | ChromaDB | 8000 |
`curl <http://localhost:8000/api/v1/heartbeat`> | | vLLM Mistral | 7060 |`curl <http://localhost:7060/health`> |

---

## Key Commands (Copy-Paste Ready)

```bash

## Full health status

./infrastructure/systemd/scripts/health_check.sh

## Start all services (systemd)

sudo ./infrastructure/systemd/scripts/enable_all.sh start

## Stop all services (coordinated)

sudo ./infrastructure/systemd/canonical_system_startup.sh stop

## View logs for a service

journalctl -u justnews@crawler -f

## Kill and restart a service

sudo systemctl restart justnews@crawler

## Database query (article count)

mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -D $MARIADB_DB \
  -e "SELECT COUNT(*) FROM articles; SELECT COUNT(*) FROM entities;"

## ChromaDB collection count

curl -s -X POST <http://localhost:8000/api/v1/collections/articles/count> \
  -H "Content-Type: application/json" -d '{}' | jq '.count'

```

---

## Success Checklist

- [ ] vLLM 7060 responding

- [ ] global.env created and sourced

- [ ] MariaDB connection OK

- [ ] ChromaDB running

- [ ] Schema initialized (tables created)

- [ ] MCP Bus healthy

- [ ] GPU Orchestrator ready

- [ ] All agent services healthy

- [ ] Live crawl test succeeded (articles in DB)

- [ ] Embeddings in ChromaDB

If all checked: ✅ **System ready for production data ingestion**

---

**Print or bookmark this card for easy reference during execution.**

**Time estimate**: ~90 minutes from Phase 1.1 to Phase 4.3 completion.

---

Last updated: December 18, 2025
