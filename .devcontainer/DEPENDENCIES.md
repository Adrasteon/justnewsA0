# Service Dependencies & Docker-Compose Configuration Guide

**Phase 1.4 Deliverable: Service Dependency Documentation**

This guide documents the service startup order, dependencies, and recommended docker-compose enhancements.

---

## Service Dependency Matrix

```
┌─────────────────────────────────────────────────────┐
│  Service Startup & Dependency Order                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. mariadb (Database)                              │
│     └─ No dependencies                              │
│     └─ Must be ready before Django migrations       │
│                                                     │
│  2. chromadb (Vector DB)                            │
│     └─ Independent, starts in parallel              │
│     └─ No hard dependency on others                 │
│                                                     │
│  3. vllm (LLM Server)                               │
│     └─ Independent, starts in parallel              │
│     └─ Depends on: HuggingFace connectivity         │
│     └─ GPU available (only hard requirement)        │
│                                                     │
│  4. app (Dev Container)                             │
│     └─ depends_on: vllm (soft, waits for start)     │
│     └─ Needs: mariadb running for migrations        │
│     └─ Can tolerate: chromadb, vllm still loading   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Current docker-compose.yaml Status

### ✅ What's Already Configured

Service specifications in `.devcontainer/docker-compose.yaml`:

```yaml
# MariaDB (Latest)
mariadb:
  image: mariadb:latest
  ports:
    - "3306:3306"
  volumes:
    - mariadb_data:/var/lib/mysql

# ChromaDB (v0.4.18 - pinned for stability)
chromadb:
  image: chromadb/chroma:0.4.18
  ports:
    - "3307:8000"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
    interval: 10s
    timeout: 5s
    retries: 3

# vLLM (Latest with GPU)
vllm:
  image: vllm/vllm-openai:latest
  gpus: all
  ports:
    - "8001:8000"

# App (Dev Container)
app:
  depends_on:
    - vllm
```

### ⏳ Recommended Enhancements

**1. Add service labels for identification:**

```yaml
services:
  app:
    labels:
      - "service.name=justnews-devcontainer"
      - "service.type=development"
      - "service.role=primary"
  
  mariadb:
    labels:
      - "service.name=justnews-database"
      - "service.type=infrastructure"
      - "service.role=critical"
      - "service.resource.type=database"
      - "service.restart.seconds=30"
  
  chromadb:
    labels:
      - "service.name=justnews-vectordb"
      - "service.type=infrastructure"
      - "service.role=optional"
      - "service.resource.type=vector-store"
      - "service.health.endpoint=/api/v1/heartbeat"
  
  vllm:
    labels:
      - "service.name=justnews-llm-server"
      - "service.type=inference"
      - "service.role=optional"
      - "service.resource.type=gpu-compute"
      - "service.health.endpoint=/v1/models"
      - "service.startup.timeout=300"
```

**2. Enhance health checks:**

```yaml
chromadb:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
    interval: 10s
    timeout: 5s
    retries: 3
    start_period: 5s

vllm:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/v1/models"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 120s  # 2 min startup grace period for model loading

mariadb:
  healthcheck:
    test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 30s
```

**3. Add resource limits (production-grade):**

```yaml
services:
  chromadb:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
  
  vllm:
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 28G
        reservations:
          cpus: '4'
          memory: 20G
  
  mariadb:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 4G
        reservations:
          cpus: '2'
          memory: 2G
```

---

## Service Startup Timeline

### Expected Startup Sequence

```
Time    Event
────────────────────────────────────────────────────────
  0s    docker-compose up -d
  0-1s  All containers created and started simultaneously
  1-5s  MariaDB initializes schema (first run)
  1-2s  ChromaDB loads in-memory store
  1-120s vLLM downloads model from HuggingFace (first run)
  5-30s  Django migrations run (waits for MariaDB)
  30-60s post-create.sh completes tasks
  60s    System ready for testing
  
  First-run with model download: 2-5 minutes total
  Subsequent starts (cache warm): 30-60 seconds total
```

### Expected Output in `docker-compose logs`

**Healthy startup (docker-compose logs -f):**

```
mariadb       | 2026-02-08 14:50:01+00:00 [Note] InnoDB: buffer pool size = 128MB
mariadb       | 2026-02-08 14:50:02+00:00 [Note] Ready for connections
mariadb       | health: echo "[+] MariaDB OK" | succeed

chromadb      | INFO:     Uvicorn running on http://0.0.0.0:8000
chromadb      | health: succeed

vllm          | INFO:vllm:vLLM OpenAI API server version 0.14.1
vllm          | INFO:vllm:Serving model Qwen/Qwen2.5-14B-Instruct-AWQ
vllm          | INFO:vllm:Loaded model successfully

app           | [✓ SUCCESS] Dev Container Initialization Complete!
```

---

## Dependency Verification Checklist

### Step-by-Step Verification Order

| Step | Check | Command | Expected | Action if Failed |
|------|-------|---------|----------|------------------|
| 1 | MariaDB socket | `python .devcontainer/diagnostic.py` | `✓ connected` | Wait 10s, retry |
| 2 | ChromaDB socket | `python .devcontainer/diagnostic.py` | `✓ connected` | Restart: `docker-compose restart chromadb` |
| 3 | ChromaDB health | `curl http://chromadb:3307/api/v1/heartbeat` | HTTP 200 | Check logs: `docker-compose logs chromadb` |
| 4 | vLLM socket | `python .devcontainer/diagnostic.py` | `✓ connected` or ⚠ | Might still be loading (wait 2-5 min) |
| 5 | vLLM models | `curl http://vllm:8001/v1/models` | Model list | Check: `docker-compose logs vllm -f` |
| 6 | Django migrations | `python manage.py showmigrations` | No pending | Rerun: `python manage.py migrate --fake-initial` |
| 7 | Full pipeline | `python tests/integration/test_devcontainer.py` | All pass | Review: `.devcontainer/SERVICE_STARTUP.md` |

---

## Startup Order Flexibility

### Services That Can Start in Parallel
- ✅ `chromadb` — No dependencies
- ✅ `vllm` — No hard dependencies (only needs HF connectivity)
- ✅ `mariadb` — No dependencies

### Services That Wait
- ⏳ `app` — Waits for `vllm` to be *runnable* (may still be loading model)
- ⏳ Django migrations — Wait for `mariadb` to be healthy (handled by post-create.sh)
- ⏳ Health checks — performed after 5-30s grace period

### What CAN'T Start Parallel
- Django can't run migrations until MariaDB accepts connections
- post-create.sh can't complete until migrations finish
- Integration tests need all services in some state

---

## Service Recovery Procedures

### MariaDB Won't Start

```bash
# Check for data corruption
docker-compose logs mariadb -n 100 | grep -i error

# If corrupted, reset and rebuild
docker-compose down
docker volume rm justnews_mariadb_data
docker-compose up -d mariadb
sleep 30
docker-compose logs mariadb | grep "Ready for connections"
```

### ChromaDB Stuck on Startup

```bash
# Check if it's a v0.4.18 health check issue
curl -v http://chromadb:3307/api/v1/heartbeat

# If API version mismatch, verify image
docker inspect $(docker-compose ps -q chromadb) | grep Image

# Should be: chromadb/chroma:0.4.18
# If not, update docker-compose.yaml and rebuild
docker-compose build --no-cache chromadb
```

### vLLM Model Download Stalled

```bash
# Check download progress
docker-compose logs vllm -f | grep -i "downloaded\|cache\|saved"

# If networking is issue, pre-download on host
huggingface-cli download Qwen/Qwen2.5-14B-Instruct-AWQ

# If CUDA memory issue
nvidia-smi -l 2  # Watch GPU usage
docker-compose logs vllm -n 50 | grep -i "cuda\|oom\|memory"
```

### app Container Exits

```bash
# Django setup issue
docker-compose logs app -n 100

# Try manual setup
docker-compose exec app /usr/local/bin/post-create.sh

# Or start fresh
docker-compose down app
docker-compose up -d app
```

---

## Integration with Tests

### Running the Full Service Test Suite

```bash
# From /app in dev container

# 1. Quick diagnostic (< 5 sec)
python .devcontainer/diagnostic.py

# 2. Full workflow test with diagnostics (30-60 sec)
python tests/integration/test_devcontainer.py

# 3. If services still loading, check status
docker-compose ps -a
docker-compose logs vllm -f --tail 20
```

### Test Output Interpretation

```
✓ Step 1: Database Connectivity & Schema
  → MariaDB connected, tables exist
  
✓ Step 2: ChromaDB Connectivity & Health
  → Port open, health check may still be initializing
  
✓ Step 3: ChromaDB Collection Operations
  → Can create/query collections, embeddings working
  
⚠ Step 4: vLLM Model Server Availability
  → Port open, models not yet loaded (still downloading)
  → Expected on first run, typically resolves in 2-5 min
  
✗ Step 5: vLLM Inference Test
  → Can't test if model still loading
  → Retry after docker-compose logs shows "Loaded model"
```

---

## Recommended docker-compose.yaml Updates

Create `docker-compose.yaml` with all enhancements (save as backup current first):

```bash
# Backup current
cp .devcontainer/docker-compose.yaml \
   .devcontainer/docker-compose.yaml.bak

# Apply enhancements (see sections above for full YAML)
# Key changes:
# 1. Add labels to all services
# 2. Enhance health checks with start_period
# 3. Add resource limits/reservations
# 4. Document startup timeouts (vllm: 300s)
```

---

## Troubleshooting Decision Tree

```
Services not responding?
│
├─ Are containers running? (docker-compose ps)
│  ├─ NO  → Start them: docker-compose up -d
│  └─ YES → Continue
│
├─ Is it MariaDB?
│  ├─ YES → Check: docker-compose logs mariadb | grep -i error
│  └─ NO  → Continue
│
├─ Is it ChromaDB?
│  ├─ YES → Verify image: grep "chromadb/chroma" docker-compose.yaml
│  │      → Should be: 0.4.18
│  └─ NO  → Continue
│
├─ Is it vLLM?
│  ├─ YES → Check download: docker-compose logs vllm | grep -i "downloading"
│  │      → First run: Wait 2-5 minutes
│  │      → Then: Retry full test
│  └─ NO  → Continue
│
└─ Still stuck?
   └─ Nuke & rebuild: docker-compose down
                      docker volume prune -f
                      docker-compose up -d
```

---

## Quick Reference Commands

```bash
# Service diagnostics
python .devcontainer/diagnostic.py

# Full test suite
python tests/integration/test_devcontainer.py

# Status
docker-compose ps -a
docker-compose ps mariadb

# Logs (most recent 50 lines)
docker-compose logs mariadb -n 50
docker-compose logs chromadb -n 50
docker-compose logs vllm -n 50

# Live logs
docker-compose logs -f

# Health check
curl -f http://chromadb:3307/api/v1/heartbeat
curl -f http://vllm:8001/v1/models

# Restart service
docker-compose restart mariadb
docker-compose restart chromadb
docker-compose restart vllm

# Full rebuild
docker-compose down
docker volume prune -f
docker-compose up -d

# Setup from scratch
docker-compose down
docker volume rm justnews_deps justnews_data mariadb_data
docker-compose up -d
```
