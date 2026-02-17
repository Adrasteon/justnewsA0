# Services Operational Checklist

**Phase 1 Deliverable: Ready-to-Deploy Service Validation Checklist**

Use this checklist to systematically verify service operational status after dev container initialization.

---

## Pre-Deployment Verification

### ✅ Step 1: Container Status

**What**: All services must be running

**How**:
```bash
docker compose ps -a
```

**Expected Output**:
```
NAME                STATUS
app                 Up
mariadb             Up (healthy)
chromadb            Up (healthy)
vllm                Up
```

**Resolution if failing**:
| Issue | Resolution |
|-------|-----------|
| Containers don't exist | Run: `docker compose up -d` |
| Container exited | Run: `docker compose restart <service>` |
| All containers exited | Run: `docker compose down && docker compose up -d` |

---

### ✅ Step 2: Service Connectivity Check

**What**: All services accepting connections on their ports

**How**:
```bash
python .devcontainer/diagnostic.py
```

**Expected Output**:
```
✓ MariaDB      → ✓ connected
✓ ChromaDB     → ✓ connected
✓ vLLM         → ✓ connected
```

**What each indicator means**:
- `✓ connected` — Port accepting connections (service ready)
- `⚠ timeout` — Service is slow or overloaded
- `✗ refused` — Service not running or wrong port
- `✗ HTTP 404` — Service running but endpoint not available (may be normal)

**Resolution if failing**:

| Service | Issue | Resolution |
|---------|-------|-----------|
| MariaDB | Connection refused | Wait 30s, then `docker compose restart mariadb` |
| ChromaDB | Connection refused | `docker compose restart chromadb` |
| vLLM | Connection refused | Service may still loading model (2-5 min first run) |
| vLLM | Still refused after 5 min | Check: `docker compose logs vllm -n 50` |

---

### ✅ Step 3: Database Schema Validation

**What**: MariaDB has required tables

**How**:
```bash
python manage.py showmigrations --list | head -20
```

**Expected Output**:
```
[X] 0001_initial
[X] 0002_add_user_columns
[X] 0003_create_articles_table
[X] 0004_add_crawl_batch
...
(20+ migrations should be marked [X])
```

**What this means**:
- `[X]` = Migration applied successfully
- `[ ]` = Migration pending (need to run migration)
- `?` = Database issue or schema corruption

**Resolution if failing**:

| Issue | Resolution |
|-------|-----------|
| Migrations pending `[ ]` | Run: `python manage.py migrate --fake-initial` |
| Migration marked `?` | Check logs: `docker compose logs mariadb -n 100` |
| Can't import Django | Ensure venv activated: `source /deps/.venv/bin/activate` |

---

### ✅ Step 4: Full Service Test

**What**: Complete pipeline integration test

**How**:
```bash
python tests/integration/test_devcontainer.py
```

**Expected Output**:
```
✓ Step 1: Database Connectivity & Schema — ✓ PASS
✓ Step 2: ChromaDB Connectivity & Health — ✓ PASS
✓ Step 3: ChromaDB Collection Operations — ✓ PASS
✓ Step 4: vLLM Model Server Availability — ✓ PASS
✓ Step 5: vLLM Inference Test — ✓ PASS

Results: 5/5 tests passed
✓ All tests passed! Pipeline fully operational.
```

**Partial Success is OK if**:
- MariaDB and ChromaDB pass (core data services)
- vLLM shows "Service may still be loading model"
- Test suggests waiting and retrying

**Resolution if failing**:

| Failure | Resolution |
|---------|-----------|
| Database test fails | See Step 3 above |
| ChromaDB test fails | `docker compose restart chromadb && sleep 5` |
| vLLM test fails (first run) | Wait 2-5 min for model download, then retry |
| vLLM test fails (repeated) | Check: `docker compose logs vllm \| grep -i cuda` |

---

## Post-Deployment Verification

### ✅ Step 5: Health Endpoint Tests

**What**: Services respond correctly to health checks

Run these commands and verify success:

```bash
# MariaDB (via Django)
python manage.py dbshell << EOF
SELECT 1;
EOF
# Expected: Prompt returns (query succeeded)

# ChromaDB (HTTP)
curl -f http://chromadb:8000/api/v2/heartbeat || curl -f http://chromadb:8000/api/v1/heartbeat
# Expected: HTTP 200

# vLLM (HTTP)
curl -f http://vllm:8001/v1/models | python -m json.tool | head -10
# Expected: JSON with model list
```

**Resolution if any fail**:
- ChromaDB 404: probe both `v2` and `v1` endpoints (API route shape may vary)
- vLLM 502/503: Model still loading (wait) or OOM (check GPU: `nvidia-smi`)
- Django fails: Check migrations were applied (Step 3)

---

### ✅ Step 5b: Pre-Build Cleanup Recovery Behavior

**What**: Confirm cleanup script handles missing Docker safely in interactive and CI contexts.

**How**:
```bash
# Interactive terminal behavior:
bash .devcontainer/scripts/pre-build-cleanup.sh
# If Docker is unavailable, script pauses for Enter and exits without changes.

# CI/non-interactive behavior:
PREBUILD_WAIT_ON_DOCKER_MISSING=false bash .devcontainer/scripts/pre-build-cleanup.sh
```

**Expected**:
- No destructive changes when Docker is unavailable
- Clear guidance to fix Docker and re-run cleanup

---

### ✅ Step 6: Resource Utilization

**What**: Services are consuming reasonable resources

**How** (from host):
```bash
docker stats --no-stream
```

**Expected ranges**:
| Service | CPU | Memory | GPU |
|---------|-----|--------|-----|
| MariaDB | 10-50% | 300-500 MB | — |
| ChromaDB | 5-20% | 200-400 MB | — |
| vLLM | 10-50% | 15-25 GB | 18-24 GB |
| app | 0.5-5% | 100-200 MB | — |

**Concerning signs**:
- Any service at `Exited` or `Created` states
- CPU stuck at 100% (likely hung)
- vLLM using >28 GB (memory leak)
- Memory constantly growing (leak)

**Resolution**:
```bash
# Kill stuck container
docker compose kill <service>

# Restart everything
docker compose restart

# Full reset if issues persist
docker compose down
docker compose up -d
sleep 60
python .devcontainer/diagnostic.py
```

---

### ✅ Step 7: Model Verification (vLLM)

**What**: Correct model loaded and ready for inference

**How**:
```bash
curl -s http://vllm:8001/v1/models | python -c "import sys, json; \
data = json.load(sys.stdin); \
print(f\"Loaded {len(data['data'])} model(s)\"); \
[print(f\"  - {m['id']}\") for m in data['data']]"
```

**Expected Output**:
```
Loaded 1 model(s)
  - Qwen/Qwen2.5-14B-Instruct-AWQ
```

**Other valid outputs**:
- First run: `Connection refused` → Wait 2-5 min, retry

**Invalid outputs**:
- Different model name → `docker compose logs vllm | grep model`
- Empty model list → Startup incomplete

---

## Operational Status Matrix

Use this to get complete system overview:

```bash
#!/usr/bin/env bash
# Save as: .devcontainer/status-check.sh

echo "=== JustNews System Status ===" 
echo ""
echo "1. Container Status:"
docker compose ps -a | tail -n +2

echo ""
echo "2. Service Connectivity:"
python .devcontainer/diagnostic.py | grep -E "^[✓⚠✗]"

echo ""
echo "3. Database:"
python manage.py showmigrations --list 2>/dev/null | grep "^\[X\]" | wc -l | xargs echo "   Migrations applied:"

echo ""
echo "4. Models:"
curl -s http://vllm:8001/v1/models | python -m json.tool 2>/dev/null | grep '"id"' | head -3

echo ""
echo "5. Resources:"
docker stats --no-stream | tail -n +2

echo ""
echo "Status check complete."
```

Run: `bash .devcontainer/status-check.sh`

---

## Common Scenarios & Responses

### Scenario: Fresh Start After Rebuild

**Checklist**:
1. ✅ All containers running? (`docker compose ps`)
2. ⏳ Wait 30-60 seconds for initialization
3. ✅ Run diagnostic: `python .devcontainer/diagnostic.py`
4. ⏳ If vLLM shows refused, wait additional 2-5 min for model download
5. ✅ Run tests: `python tests/integration/test_devcontainer.py`
6. ✅ Check resources: `docker stats --no-stream`

**Expected timeline**:
- 0-30s: Services starting
- 30-60s: MariaDB ready, Django migrations running
- 1-2m: ChromaDB ready
- 2-5m: vLLM model loading (first run only)
- 5m+: All services ready, tests should pass

---

### Scenario: Partial Service Failure (e.g., vLLM Not Ready)

**Status**: OK to proceed if:
- ✅ MariaDB working (database operations possible)
- ✅ ChromaDB working (vector store functioning)
- ⏳ vLLM still loading (wait and retry)

**Next steps**:
```bash
# Check vLLM logs for progress
docker compose logs vllm -f --tail 30

# Look for:
# - Download progress (good)
# - CUDA errors (bad - may need restart)
# - Just started loading (2-5 min wait)

# Retry test in 2 minutes
sleep 120
python tests/integration/test_devcontainer.py
```

---

### Scenario: Services Keep Crashing

**Diagnostic steps**:
```bash
# 1. Check what's happening
docker compose logs app -n 100
docker compose logs mariadb -n 100
docker compose logs vllm -n 100

# 2. Look for patterns:
# - OOM: "Killed" or "out of memory"
# - Startup race: "Connection refused initially then recovered"
# - Corruption: "Table corrupted" or "InnoDB recovery"

# 3. If specific service crashing:
docker compose logs <service> -f --tail 50

# 4. Hard reset if persistent
docker compose down
docker volume prune -f
docker system prune -f
docker compose up -d
```

---

## Success Criteria

### ✅ Green Light (Production Ready)

All of these must be true:
- ✅ `docker compose ps` shows all containers `Up`
- ✅ `python .devcontainer/diagnostic.py` shows all `✓ connected`
- ✅ `python tests/integration/test_devcontainer.py` shows `5/5 tests passed`
- ✅ Database has 20+ migrations applied
- ✅ vLLM reports correct model name
- ✅ Resources within expected ranges

**Action**: Ready for development/testing

### ⚠️ Yellow Light (Partial Ready)

Some optional services not ready yet:
- ⚠️ vLLM still loading model (port open but HTTP not responding)
- ⚠️ One or two tests pending (database and ChromaDB working)

**Action**: Wait 2-5 minutes and retry, or proceed with database-only work

### ✗ Red Light (Not Ready)

Critical service down:
- ✗ MariaDB connection refused after 60s
- ✗ Django migrations show pending `[ ]` after restart
- ✗ ChromaDB can't create collections
- ✗ Multiple memory errors in container logs

**Action**: Review `.devcontainer/SERVICE_STARTUP.md`, attempt recovery, or escalate

---

## Automated Monitoring Script

Save as `.devcontainer/monitor.sh`:

```bash
#!/usr/bin/env bash
# Continuous service monitoring

INTERVAL=${1:-10}  # seconds

while true; do
  clear
  echo "=== JustNews Service Monitor ==="
  echo "Updated: $(date)"
  echo ""
  
  # Status
  docker compose ps -a | tail -n +2 | awk '{print $1, $2}'
  
  # Quick health
  echo ""
  python .devcontainer/diagnostic.py | grep -E "^[✓✗⚠]" | head -3
  
  # GPU (if available)
  if command -v nvidia-smi &> /dev/null; then
    echo ""
    nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total \
      --format=csv,noheader,nounits | awk '{print "GPU: " $1"% (" $2 "MB/" $3 "MB)"}'
  fi
  
  sleep $INTERVAL
done
```

Run: `bash .devcontainer/monitor.sh 5` (updates every 5 seconds)

---

## Troubleshooting Fast Track

**Issue**: "Services working but seems slow"
```bash
# Check if model is offloaded:
nvidia-smi
# vLLM using less than 18GB? Model might be swapping

# Check load:
docker stats --no-stream | grep -E "vllm|chromadb"
# Either CPU >50% or memory maxed out?
```

**Issue**: "Can't query ChromaDB"
```bash
# Verify it's the right endpoint:
curl -v http://chromadb:8000/api/v2/heartbeat || curl -v http://chromadb:8000/api/v1/heartbeat
# Should return HTTP 200 on one of the two routes
```

**Issue**: "vLLM keeps timing out"
```bash
# Model download stuck or failed:
docker compose logs vllm | grep -i "error\|failed\|warning"

# Check network:
curl -I https://huggingface.co
# If fails, network is issue (not service)
```

---

## When All Else Fails

```bash
# Nuclear option: Full reset

docker compose down                    # Stop all services
docker volume prune -f                 # Remove unused volumes  
docker system prune -f -a              # Clean up everything
docker pull nvidia/cuda:12.4.1-devel-ubuntu22.04
docker pull mariadb:latest
docker pull chromadb/chroma:latest
docker pull vllm/vllm-openai:latest    # Pre-pull images
docker compose up -d                   # Start fresh
sleep 120                              # Wait for init
python .devcontainer/diagnostic.py     # Check status
```

Then reference `.devcontainer/SERVICE_STARTUP.md` for any remaining issues.

---

## Sign-Off Checklist

**For approvers/leads**:

- [ ] All services running (`docker compose ps` shows all `Up`)
- [ ] Diagnostic passes (`.devcontainer/diagnostic.py` all `✓`)
- [ ] Integration tests pass (5/5 in `test_devcontainer.py`)
- [ ] No error messages in last 20 lines of any log
- [ ] GPU (if applicable) showing appropriate VRAM usage
- [ ] Can manually query database, ChromaDB, and vLLM
- [ ] Performance acceptable (vLLM inference <2s, ChromaDB search <1s)

**Comment template**:
```
✅ Services Operational Checklist Complete

- Database: ✅ 25/25 migrations applied
- MariaDB: ✅ Healthy (324 MB RAM)
- ChromaDB: ✅ Healthy (280 MB RAM)  
- vLLM: ✅ Model loaded (Qwen 2.5 14B)
- GPU: ✅ 22.5 GB VRAM utilized
- Tests: ✅ 5/5 passed

Ready for: Development/Testing/Staging
Deployment approval: Yes
```
