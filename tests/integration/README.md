# Integration Testing Guide

**Date**: February 8, 2026  
**Version**: 1.0  
**Audience**: Developers, QA Engineers, DevOps

---

## 📋 Quick Start

### One-Minute Test

Verify all services are operational:

```bash
cd /app
python .devcontainer/diagnostic.py
```

Expected output:
```
✓ MariaDB      → connected
✓ ChromaDB     → connected  
✓ vLLM         → connected
```

### Five-Minute Test

Run full integration test suite:

```bash
cd /app
python tests/integration/test_devcontainer.py
```

Expected output:
```
✓ PASS  database (schema validated)
✓ PASS  chromadb_connectivity (port 3307 open)
✓ PASS  chromadb_operations (collection create/query)
✓ PASS  vllm_availability (model loaded)
✓ PASS  inference (prompt response 50+ tokens)

Results: 5/5 tests passed
```

---

## 🏗️ Test Architecture

### Test Pyramid

```
                  ▲
                 ╱ ╲      End-to-End Tests
                ╱   ╲     - Full pipeline
               ╱     ╲    - Real inference
              ╱───────╲
             ╱ Component Tests (Integration)
            ╱  - Database connectivity
           ╱   - Service ports open
          ╱    - API health checks
         ╱─────
        ╱ Unit Tests
       ╱  - Code logic
      ╱   - Error handling
     ╱─────
```

### Test Coverage

| Layer | Test | File | Purpose |
|-------|------|------|---------|
| **Component** | MariaDB connectivity | `test_devcontainer.py::test_database_connectivity()` | Verify DB accessible, schema present |
| **Component** | ChromaDB connectivity | `test_devcontainer.py::test_chromadb_connectivity()` | Verify vector DB port/health |
| **Component** | vLLM availability | `test_devcontainer.py::test_vllm_availability()` | Verify LLM server running |
| **Integration** | ChromaDB operations | `test_devcontainer.py::test_chromadb_operations()` | Create collection, store embeddings |
| **Integration** | vLLM inference | `test_devcontainer.py::test_inference()` | Full prompt → response pipeline |
| **E2E** | Article flow | `tests/integration/article_flow_test.py` | Crawl → Store → Embed → Query (TBD Phase 2) |
| **Performance** | Baseline capture | `tests/integration/baseline_capture.py` | Measure throughput/latency (TBD Phase 2) |

---

## 🚀 Running Tests

### Standard Test Run

```bash
# Navigate to repo
cd /app

# Run all integration tests
python tests/integration/test_devcontainer.py

# Expected: 5/5 passing in ~30 seconds (services must be running)
```

### Test Results Interpretation

**All 5/5 Passing** ✓
```
Results: 5/5 tests passed
✓ All tests passed! Pipeline fully operational.
```
- Action: Ready for development or deployment
- Next: Proceed to Phase 2 performance baselines

**4/5 Passing** (1 failing)
```
Results: 4/5 tests passed
⚠ Partial success. Core services responding but some features unavailable.
   Check .devcontainer/SERVICE_STARTUP.md for troubleshooting.
```
- Action: Investigate failing test details above results
- Next: Check .devcontainer/SERVICE_STARTUP.md for resolution
- Common: vLLM still loading model (wait 2-5 min), ChromaDB container crashed

**3/5 or fewer Passing** (Critical failure)
```
Results: 2/5 tests passed
✗ Critical services not responding. See troubleshooting guide.
```
- Action: Check service status immediately
- Command: `docker-compose ps -a` (are containers running?)
- Next: Review `.devcontainer/DEPENDENCIES.md` startup sequence

---

## 🧪 Individual Test Details

### Test 1: Database Connectivity

**File**: `test_devcontainer.py::test_database_connectivity()`

**What it does**:
1. Tries to connect via Django ORM (if Django configured)
2. Executes `SELECT 1` to verify database responsiveness
3. Counts tables in information_schema to validate schema

**Expected Output**:
```
→ Step 1: Database Connectivity & Schema
  ────────────────────────────────────────────────────────────
  ✓ MariaDB connection successful
  ✓ Database has 42 tables
```

**Pass Criteria**: 
- Django connection successful OR socket connection to mariadb:3306 succeeds
- Table count > 5 (indicates migrations ran)

**Failure Scenarios**:
| Error | Likely Cause | Resolution |
|-------|--------------|-----------|
| `Connection refused` | MariaDB not running | `docker-compose restart mariadb` |
| `No tables found` | Migrations haven't run | Run `python manage.py migrate --fake-initial` |
| `Django settings not configured` | Expected in non-Django context | Falls back to socket check |

---

### Test 2: ChromaDB Connectivity

**File**: `test_devcontainer.py::test_chromadb_connectivity()`

**What it does**:
1. Checks ChromaDB HTTP port (3307) is open via socket
2. Hits health endpoint: `/api/v1/heartbeat`
3. Verifies version matches expected (0.4.18)

**Expected Output**:
```
→ Step 2: ChromaDB Connectivity & Health
  ────────────────────────────────────────────────────────────
  ✓ ChromaDB port is responding (3307)
  ✓ Health check passed (200 OK)
  ✓ Version verified: 0.4.18
```

**Pass Criteria**:
- Port 3307 open and TCP handshake succeeds
- Health endpoint returns HTTP 200
- Version header matches pinned version

**Failure Scenarios**:
| Error | Likely Cause | Resolution |
|-------|--------------|-----------|
| `Connection refused` | Container not running | `docker-compose restart chromadb` |
| `404 Not Found` | Wrong version/API changed | Check docker-compose.yaml has `chromadb:0.4.18` |
| `502 Bad Gateway` | Container crashed | Check logs: `docker-compose logs chromadb` |

---

### Test 3: ChromaDB Operations

**File**: `test_devcontainer.py::test_chromadb_operations()`

**What it does**:
1. Creates ChromaDB HTTP client
2. Creates a test collection ("test_collection")
3. Adds sample documents with embeddings
4. Queries for semantic similarity
5. Validates results are returned

**Expected Output**:
```
→ Step 3: ChromaDB Collection Operations
  ────────────────────────────────────────────────────────────
  ✓ Successfully connected to ChromaDB client
  ✓ Created test collection
  ✓ Added 3 documents with embeddings
  ✓ Semantic query returned 2 results
```

**Pass Criteria**:
- Client connects without auth errors
- Collection creation succeeds (not duplicate error if re-run)
- Documents store and retrieve successfully
- Query returns n_results > 0

**Failure Scenarios**:
| Error | Likely Cause | Resolution |
|-------|--------------|-----------|
| `Could not connect to Chroma server` | Service health degraded | Wait 5 sec, restart: `docker-compose restart chromadb` |
| `Embedding failed` | Model not loaded in ChromaDB | Check container logs for errors |
| `Collection already exists` | First run after test cleanup | Expected on subsequent runs; collection created or reused |

---

### Test 4: vLLM Availability

**File**: `test_devcontainer.py::test_vllm_availability()`

**What it does**:
1. Checks vLLM HTTP port (8001) is open
2. Hits `/v1/models` endpoint to list loaded models
3. Verifies Qwen 2.5 14B model is loaded

**Expected Output**:
```
→ Step 4: vLLM Model Server Availability
  ────────────────────────────────────────────────────────────
  ✓ vLLM port is responding (8001)
  ✓ Models endpoint accessible
  ✓ Qwen/Qwen2.5-14B-Instruct-AWQ model loaded
```

**Pass Criteria**:
- Port 8001 open (socket connection succeeds)
- `/v1/models` returns HTTP 200
- Response includes Qwen model in models list

**Failure Scenarios**:
| Error | Likely Cause | Resolution |
|-------|--------------|-----------|
| `Connection refused` | Container not running or still initializing | Wait 5 min for model download, `docker-compose logs vllm` for progress |
| `Connection timeout` | Model downloading from HuggingFace (~15GB over internet) | First run takes 5-10 min; be patient |
| `vLLM not responding (may still be loading)` | Model load in progress | Expected during first startup; wait ⏳ |

---

### Test 5: vLLM Inference

**File**: `test_devcontainer.py::test_inference()`

**What it does**:
1. Sends prompt to vLLM via `/v1/completions` endpoint
2. Waits for response (completion text)
3. Validates response has > 0 tokens generated
4. Measures response latency

**Expected Output**:
```
→ Step 5: vLLM Inference Test
  ────────────────────────────────────────────────────────────
  ✓ Inference successful
    Response: The impact of machine learning extends across numerous...
```

**Pass Criteria**:
- HTTP request succeeds
- Response contains "choices[0].text" with generated text
- Generated text is > 10 tokens

**Failure Scenarios**:
| Error | Likely Cause | Resolution |
|-------|--------------|-----------|
| `Connection refused` | vLLM not running | Start container, wait for model load |
| `Request timeout (60s exceeded)` | Model generation very slow | GPU may be under load; reduce batch size or wait for idle |
| `HTTP 503 Service Unavailable` | vLLM queue exceeded (too many concurrent requests) | Normal under load; test retry in 30 sec |
| `Empty response` | Model returned empty completion | Model configuration issue; check vLLM logs |

---

## 🔄 Test Workflow (Phase 2)

### Pre-Test Checklist

- [ ] Services are running: `docker-compose ps -a` shows all ✓
- [ ] At least 5 min have passed since container start (model download)
- [ ] No other tests are running (avoid resource contention)
- [ ] Enough disk space for temporary test files (/tmp must have > 100MB free)

### Run Tests

```bash
# Start from repo root
cd /app

# Show service status first
docker-compose ps -a

# Run diagnostic to see what's working
python .devcontainer/diagnostic.py

# Run full test suite
python tests/integration/test_devcontainer.py

# Capture output for reporting
python tests/integration/test_devcontainer.py > /tmp/test_results.txt 2>&1
```

### Interpret Results

Check **Results Summary** at bottom:

```
Results: X/5 tests passed
```

- **5/5** → All green ✓, ready for proceeding
- **4/5** → Check which test failed, see section above
- **3/5 or less** → Critical issue; don't deploy

### Troubleshoot Failed Tests

1. **Identify failing test** from results (e.g., "Step 2: ChromaDB")
2. **Look up in table above** for likely causes
3. **Try resolution command** (e.g., `docker-compose restart chromadb`)
4. **Re-run test** after 5 second wait: `python tests/integration/test_devcontainer.py`

**If still failing**:
```bash
# Check service logs
docker-compose logs chromadb -n 50

# Check service health
python .devcontainer/diagnostic.py

# Restart all services
docker-compose restart

# Wait 60 sec
sleep 60

# Re-test
python tests/integration/test_devcontainer.py
```

---

## 📊 Performance Baseline Testing (Phase 2 Later)

### Baseline Capture

When all 5/5 tests pass consistently, capture performance baselines:

```bash
# Not yet implemented - placeholder for Phase 2 tasks
# python tests/integration/baseline_capture.py \
#   --output tests/integration/baselines/baseline_$(date +%Y-%m-%d).json \
#   --articles 1000
```

See [Performance Baselines Guide](../docs/performance-baselines.md) for detailed metrics.

---

## 🚩 Common Issues & Quick Fixes

### Issue: Database Test Fails with "settings not configured"

**Symptom**:
```
✗ Database test failed: Requested setting DATABASES, but settings are not configured
```

**Solution**:
```bash
# Set Django settings module
export DJANGO_SETTINGS_MODULE=justnews_publisher.settings

# Re-run
python tests/integration/test_devcontainer.py
```

---

### Issue: ChromaDB Returns 404

**Symptom**:
```
✗ ChromaDB connectivity failed: 404 Not Found
```

**Cause**: Version mismatch (old API version still running)

**Solution**:
```bash
# Check current version
docker-compose logs chromadb | grep "Chroma" | head -1

# Restart with correct version
docker-compose restart chromadb

# Verify version in logs
docker-compose logs chromadb | grep -i version

# Should show: "Running Chroma server: 0.4.18"
```

---

### Issue: vLLM Says "Model Loading"

**Symptom**:
```
⚠ vLLM not responding (may still be loading model)
```

**Solution**: This is **normal on first startup**. Wait:

```bash
# Show progress
docker-compose logs vllm -f

# Wait for this message:
# "Qwen/Qwen2.5-14B-Instruct-AWQ loaded successfully"

# Then re-run tests after it appears
python tests/integration/test_devcontainer.py
```

Expected wait time: **2-10 minutes** depending on internet speed (15GB download)

---

### Issue: All Tests Fail with Connection Refused

**Symptom**:
```
✗ MariaDB → Connection refused
✗ ChromaDB → Connection refused  
✗ vLLM → Connection refused
```

**Cause**: Docker containers not running

**Solution**:
```bash
# Check what's running
docker-compose ps -a

# If any say "Exit X" → crashed
# Try full restart:
docker-compose down
docker-compose up -d

# Wait for startup
sleep 60

# Try again
python tests/integration/test_devcontainer.py
```

---

## 🔬 Advanced: Manual Testing

### Manual Database Check

```python
python3 << 'EOF'
import os
os.environ["DJANGO_SETTINGS_MODULE"] = "justnews_publisher.settings"
import django
django.setup()

from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) FROM articles")
    count = cursor.fetchone()[0]
    print(f"Articles in database: {count}")
EOF
```

### Manual ChromaDB Check

```python
python3 << 'EOF'
import chromadb
client = chromadb.HttpClient(host="chromadb", port=3307)
print(f"ChromaDB connected: {client.get_version()}")

# List collections
collections = client.list_collections()
print(f"Collections: {[c.name for c in collections]}")
EOF
```

### Manual vLLM Check

```bash
# Direct HTTP request
curl -X POST http://vllm:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "prompt": "What is AI?",
    "max_tokens": 50
  }' | python3 -m json.tool
```

---

## 📚 References

- [Phase 1: Service Validation](./.devcontainer/README.md)
- [Service Startup Troubleshooting](./.devcontainer/SERVICE_STARTUP.md)
- [Service Dependencies](./.devcontainer/DEPENDENCIES.md)
- [Operations Checklist](./.devcontainer/services-operational-checklist.md)
- [Performance Baselines](../docs/performance-baselines.md)

---

## ✅ Test Readiness Checklist

Before Phase 2 testing phase:

- [ ] Run `python tests/integration/test_devcontainer.py` 3 times consecutively
- [ ] All 3 runs show 5/5 passing
- [ ] No intermittent failures
- [ ] Document any environment-specific issues encountered
- [ ] Confirm troubleshooting steps work as documented above
- [ ] Ready for performance baseline capture

---

**Next Phase**: Phase 3 (Operational Runbooks) - Expected start after all 5 tests consistent for 1 week
