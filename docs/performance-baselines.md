# Performance Baselines & Regression Testing

**Date Created**: February 8, 2026  
**Last Updated**: February 8, 2026  
**Status**: Phase 2 Foundation

---

## 📊 Overview

This document establishes baseline performance metrics for the JustNews pipeline. These measurements serve as regression detection thresholds and help identify infrastructure bottlenecks.

### Critical Measurement Points

- **Article Ingestion Latency**: Time from crawl completion to database store
- **Embedding Generation Latency**: Time to convert article text to embeddings
- **Query Response Time**: Time for semantic search (query → embeddings → retrieval)
- **GPU Memory Utilization**: VRAM consumption during inference
- **System Resource Consumption**: CPU, disk I/O, MariaDB connection pooling

---

## 🎯 Baseline Metrics (To Be Captured)

### 1. Article Ingestion Pipeline

| Metric | Target | Threshold (⚠ warning) | Threshold (✗ critical) | Notes |
|--------|--------|----------------------|------------------------|-------|
| **Crawl → Store** | < 500ms | < 1s | > 2s | Per article, excludes network |
| **Batch Insert (100 articles)** | < 3s | < 5s | > 10s | MariaDB transaction throughput |
| **Schema Validation** | < 50ms | < 100ms | > 200ms | per article |
| **Duplicate Detection** | < 100ms | < 200ms | > 500ms | URL similarity check |

**Measurement Method**:
```python
import time
start = time.perf_counter()
# Insert 100 articles via Django ORM
articles = [create_article(data) for data in batch]
Article.objects.bulk_create(articles, batch_size=50)
duration = time.perf_counter() - start
```

**Expected Environment**:
- MariaDB: 10.11+, local container network
- Django: 5.2, connection pooling enabled
- Storage: SSD (local container volume)

---

### 2. Embedding Generation (ChromaDB)

| Metric | Target | Threshold (⚠ warning) | Threshold (✗ critical) | Notes |
|--------|--------|----------------------|------------------------|-------|
| **Single Article Embedding** | < 200ms | < 500ms | > 1.5s | Text → vector conversion |
| **Batch (10 articles)** | < 1.5s | < 3s | > 5s | Text chunking + embeddings |
| **Collection Query** | < 100ms | < 200ms | > 500ms | Semantic search latency |
| **Embedding Dimension** | 1536 | — | — | Vector database dimension |
| **Collection Size** | 50K+ embeddings | — | — | Test with realistic scale |

**Measurement Method**:
```python
import time
import chromadb

client = chromadb.HttpClient(host="chromadb", port=3307)
collection = client.get_or_create_collection("articles")

# Single embedding
texts = ["Sample article content about AI"]
start = time.perf_counter()
results = collection.add(documents=texts, ids=["1"])
duration = time.perf_counter() - start

# Query
query_texts = ["artificial intelligence"]
start = time.perf_counter()
results = collection.query(query_texts=query_texts, n_results=10)
duration = time.perf_counter() - start
```

**Expected Environment**:
- ChromaDB: v0.4.18 (pinned for stability)
- Client: HTTP API (docker service name "chromadb")
- Network: Internal Docker network (low latency)

---

### 3. vLLM Inference Performance

| Metric | Target | Threshold (⚠ warning) | Threshold (✗ critical) | Notes |
|--------|--------|----------------------|------------------------|-------|
| **Model Load Time (First)** | 2–5 min | < 8 min | > 15 min | Qwen 2.5 14B from HuggingFace |
| **Warmup Generation** | < 3s | < 5s | > 10s | First token generation |
| **Batch Inference (5 items)** | < 4s | < 7s | > 15s | Prompt → completion |
| **Token Generation Rate** | > 20 tok/s | > 15 tok/s | < 10 tok/s | Output tokens per second |
| **Max Concurrent Requests** | 5+ | 3+ | < 2 | Simultaneous inference calls |
| **GPU Memory Peak** | ~21GB | < 23GB | > 24GB | RTX 3090 headroom |

**Measurement Method**:
```python
import time
import requests
import json

url = "http://vllm:8001/v1/completions"
headers = {"Content-Type": "application/json"}

# Measure first token latency
payload = {
    "model": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "prompt": "What is machine learning?",
    "max_tokens": 100,
    "temperature": 0.7,
}

start = time.perf_counter()
response = requests.post(url, json=payload, headers=headers, timeout=30)
first_token_latency = time.perf_counter() - start

# Measure token generation rate
data = response.json()
tokens_generated = len(data["choices"][0]["text"].split())
throughput = tokens_generated / first_token_latency

# Monitor GPU with: nvidia-smi --query-gpu=memory.used --format=csv,noheader
```

**Expected Environment**:
- Model: Qwen/Qwen2.5-14B-Instruct-AWQ (quantized, ~14GB)
- Device: NVIDIA RTX 3090 (24GB VRAM, compute 8.6)
- vLLM: 0.14.1, OpenAI-compatible API

---

### 4. System Resource Utilization

| Metric | Target | Threshold (⚠ warning) | Threshold (✗ critical) | Notes |
|--------|--------|----------------------|------------------------|-------|
| **Host CPU Usage** | 30–60% | < 80% | > 95% | During inference|
| **Host Memory Usage** | < 60% | < 80% | > 90% | Including container overhead |
| **GPU Memory Free** | > 2GB | > 1GB | < 500MB | Ensure headroom for async load |
| **Disk I/O (MariaDB)** | < 100 IOPS | < 200 IOPS | > 500 IOPS | During batch ingestion |
| **MariaDB Connections** | 5–10 | < 20 | > 50 | Connection pool exhaustion |

**Measurement Method**:
```bash
# CPU / Memory
top -b -n 1 | grep Cpu | tail -1
free -h

# GPU Memory
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader

# Disk I/O
iostat -x 1 5

# MariaDB Connections
mysql -u root -p -e "SHOW PROCESSLIST; SHOW STATUS LIKE 'Threads_connected';"
```

**Monitoring during load test**:
```python
import subprocess
import time

def get_gpu_memory():
    """Get current GPU memory in GB"""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    return int(result.stdout.strip()) / 1024

def get_cpu_percent():
    """Get CPU usage percentage"""
    result = subprocess.run(
        ["top", "-b", "-n", "1"],
        capture_output=True, text=True
    )
    for line in result.stdout.split('\n'):
        if 'Cpu(s)' in line:
            # Parse like: "Cpu(s): 45.5%us, 12.3%sy, ..."
            user_pct = float(line.split()[1].replace('%us,', ''))
            return user_pct
    return 0
```

---

## 📈 Baseline Capture Procedure

### Setup Phase

1. **Clean Environment**:
   ```bash
   # Remove old test data
  docker compose down -v
  docker compose up -d
   
   # Wait for service health
   python .devcontainer/diagnostic.py
   sleep 30  # Extra margin for ChromaDB initialization
   ```

2. **Verify Services**:
   ```bash
   python tests/integration/test_devcontainer.py
   # All 5 tests should pass with ✓
   ```

3. **Initialize Test Data**:
   ```python
   # Create realistic test corpus (1K articles)
   from tests.integration.baseline_runner import create_test_corpus
   corpus = create_test_corpus(count=1000)
   ```

### Measurement Phase

Execute the baseline capture script:

```bash
python tests/integration/baseline_capture.py \
  --output tests/integration/baselines/baseline_2026-02-08.json \
  --articles 1000 \
  --verbose
```

**Expected Output**:
```json
{
  "capture_date": "2026-02-08T15:30:00Z",
  "environment": {
    "gpu": "NVIDIA RTX 3090",
    "mariadb_version": "10.11.6",
    "chromadb_version": "0.4.18",
    "vllm_version": "0.14.1"
  },
  "metrics": {
    "ingestion": {
      "articles_per_second": 125.3,
      "avg_latency_ms": 8.1,
      "p99_latency_ms": 15.2
    },
    "embedding": {
      "embeddings_per_second": 45.6,
      "avg_latency_ms": 21.9,
      "p99_latency_ms": 35.7
    },
    "inference": {
      "tokens_per_second": 24.3,
      "first_token_latency_ms": 1250,
      "batch_throughput": 5.2
    },
    "resources": {
      "gpu_peak_memory_gb": 21.8,
      "cpu_avg_percent": 45.3,
      "memory_avg_percent": 62.1
    }
  }
}
```

---

## 🚨 Regression Detection

### Weekly Regression Check

```bash
# Capture current metrics
python tests/integration/baseline_capture.py \
  --output /tmp/current_baseline.json

# Compare with last baseline
python tests/integration/regression_check.py \
  --baseline tests/integration/baselines/baseline_2026-02-08.json \
  --current /tmp/current_baseline.json \
  --threshold-pct 10
```

**Example Regression Detection**:
```
╔════════════════════════════════════════════════════╗
║   Regression Analysis Report                       ║
╚════════════════════════════════════════════════════╝

Baseline: 2026-02-08
Current:  2026-02-15
Change:   +7 days

Ingestion Throughput:
  ✗ REGRESSION: 125.3 art/s → 98.2 art/s (-21.6%)
  Threshold: ±10%
  Action: Investigate MariaDB connection pooling

Inference Throughput:
  ✓ OK: 24.3 tok/s → 25.1 tok/s (+3.3%)
  Within threshold

GPU Memory:
  ✓ OK: 21.8GB → 21.9GB (+0.5%)
  Acceptable drift

Overall: ✗ 1 regression detected
  Recommended action: Scale MariaDB pool, review query optimization
```

---

## 🎪 Load Testing Scenarios

### Scenario 1: Typical Daily Load

**Description**: Simulate a normal operating day  
**Duration**: 1 hour  
**Load Pattern**:
- Ingestion: 100 articles/min for first 30 min
- Queries: 10 semantic searches/min throughout
- Inference: 5 requests/min for summarization

**Success Criteria**:
- All metrics within "⚠ warning" threshold
- No database connection pool exhaustion
- GPU memory stays below 23GB
- No errors in application logs

### Scenario 2: Peak Load

**Description**: Sudden traffic spike (e.g., breaking news)  
**Duration**: 10 minutes  
**Load Pattern**:
- Ingestion: 500 articles/min
- Queries: 50 semantic searches/min
- Inference: 20 requests/min for different models

**Success Criteria**:
- Database handles spike without queue backlog
- vLLM queues requests gracefully (HTTP 503 if overloaded)
- No memory leaks (GPU/host memory stable after cooldown)
- Recovery time < 5 min after peak

### Scenario 3: Sustained High Load

**Description**: Extended high throughput (e.g., bulk backfill)  
**Duration**: 4 hours  
**Load Pattern**:
- Ingestion: 200 articles/min continuous
- Queries: Minimal (20/min)
- Inference: Minimal (2/min)

**Success Criteria**:
- Ingestion rate remains stable (no degradation)
- Database connections don't leak
- Storage doesn't fill up unexpectedly
- CPU/memory heat dissipation acceptable

---

## 📋 Baseline Checklist

Before deploying to production, verify:

- [ ] **Baseline metrics captured** with representative load (1000+ articles)
- [ ] **All 5 integration tests passing** consistently (3x runs)
- [ ] **Resource peaks documented** (GPU, CPU, memory peaks during load)
- [ ] **Regression thresholds set** (each metric has ±10% warning, ±20% critical)
- [ ] **Load test scenarios executed** successfully
- [ ] **Performance graphs generated** (ingestion/latency/throughput trends)
- [ ] **Alerting configured** (thresholds in monitoring system)
- [ ] **Baseline committed to git** for version tracking

---

## 🔍 Continuous Monitoring

### Prometheus Metrics (When Available)

```yaml
# Key metrics to expose
- articles_ingested_total
- article_ingestion_latency_seconds (histogram)
- embeddings_generated_total
- embedding_generation_latency_seconds (histogram)
- inference_requests_total
- inference_latency_seconds (histogram)
- inference_tokens_per_second (gauge)
- gpu_memory_used_bytes (gauge)
- db_connection_pool_size (gauge)
- db_query_latency_seconds (histogram)
```

### Dashboard Queries

```sql
-- Ingestion rate
SELECT COUNT(*) as articles_per_min 
FROM articles 
WHERE created_at > NOW() - INTERVAL 1 MINUTE;

-- Query latency percentiles
SELECT 
  PERCENTILE(query_duration_ms, 50) as p50,
  PERCENTILE(query_duration_ms, 95) as p95,
  PERCENTILE(query_duration_ms, 99) as p99
FROM query_metrics
WHERE timestamp > NOW() - INTERVAL 1 HOUR;

-- GPU utilization
-- Via nvidia-smi monitoring
nvidia-smi dmon -s pucvmet
```

---

## 📝 References

- [Service Startup Guide](./.devcontainer/SERVICE_STARTUP.md)
- [Integration Testing](../tests/integration/README.md)
- [CI/CD Pipeline](./.github/workflows/performance-tests.yml)
- [Monitoring Setup](./operations/MONITORING.md) (Phase 3)

---

**Next Steps**:
1. Execute baseline capture once Phase 2 testing infrastructure is ready
2. Establish CI/CD pipeline for continuous regression detection (Phase 5)
3. Review thresholds quarterly as infrastructure evolves
