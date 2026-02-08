# Monitoring & Alerting Setup

**Date**: February 8, 2026  
**Version**: 1.0  
**Audience**: Operations Engineers, DevOps, On-Call Support

---

## 📊 Key Metrics to Monitor

### 1. Database (MariaDB)

**Critical Metrics**:

| Metric | Target | ⚠ Warning | ✗ Critical | Check Command |
|--------|--------|-----------|-----------|----------------|
| **Connections Usage** | 5–20 | 30 | > 50 | `SHOW STATUS LIKE 'Threads_connected';` |
| **Query Latency (p99)** | < 100ms | < 500ms | > 1000ms | Slow query log |
| **Row Inserts/sec** | 50–100 | 20 | < 5 | `SHOW STATUS LIKE 'Questions';` (delta) |
| **Replication Lag** | 0 | < 5s | > 10s | `SHOW SLAVE STATUS;` |
| **Disk I/O (IOPS)** | 20–100 | 200 | > 500 | `iostat -x 1 5` |
| **Memory Usage** | < 60% | < 75% | > 85% | `free -h` |

**Log Locations**:
- Errors: `docker-compose logs mariadb | grep -i error`
- Slow queries: `/var/lib/mysql/hostname-slow.log` (if enabled)
- General log: `/var/lib/mysql/hostname.log` (if enabled)

**Monitoring Queries**:

```sql
-- Show current connections
SHOW PROCESSLIST;

-- Count slow queries
SELECT COUNT(*) FROM mysql.slow_log;

-- Check table sizes
SELECT 
  TABLE_NAME, 
  ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024) AS MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'justnews'
ORDER BY MB DESC;

-- Check for locks
SHOW ENGINE INNODB STATUS\G

-- Monitor connections over time
SELECT VARIABLE_VALUE FROM INFORMATION_SCHEMA.GLOBAL_STATUS 
WHERE VARIABLE_NAME = 'Threads_connected';
```

---

### 2. Vector Database (ChromaDB)

**Critical Metrics**:

| Metric | Target | ⚠ Warning | ✗ Critical | Check Method |
|--------|--------|-----------|-----------|--------------|
| **Health Status** | 200 OK | — | != 200 | `curl /api/v1/heartbeat` |
| **Response Latency** | < 200ms | < 500ms | > 1000ms | Test query timing |
| **Collection Count** | 50K+ | — | 0 (empty) | `/api/v1/collections` |
| **Memory Usage** | 1–4GB | < 6GB | > 7GB | `docker stats chromadb` |
| **Error Rate** | 0% | < 1% | > 5% | Log analysis |
| **API Uptime** | 99.9% | > 99% | < 95% | Weekly calculation |

**Log Locations**:
- Container logs: `docker-compose logs chromadb -f`
- Errors: `docker-compose logs chromadb | grep -i error`

**Health Checks**:

```bash
# Quick health check
curl -s http://chromadb:3307/api/v1/heartbeat | python3 -m json.tool

# Check version
curl -s http://chromadb:3307/api/v1/heartbeat | jq '.version'

# List all collections
curl -s http://chromadb:3307/api/v1/collections | python3 -m json.tool | jq '.[].name'

# Collection stats (detailed)
curl -s http://chromadb:3307/api/v1/collections | python3 << 'EOF'
import sys, json
data = json.load(sys.stdin)
for col in data:
    print(f"{col['name']}: {col.get('metadata', {}).get('count', 'unknown')} embeddings")
EOF
```

**Monitoring Script** (run periodically):

```bash
#!/bin/bash
# Monitor ChromaDB health

CHROMADB_URL="http://chromadb:3307"
RESPONSE=$(curl -s -w "\n%{http_code}" "$CHROMADB_URL/api/v1/heartbeat")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -1)

if [ "$HTTP_CODE" = "200" ]; then
  echo "✓ ChromaDB healthy: $BODY"
else
  echo "✗ ChromaDB unhealthy (HTTP $HTTP_CODE)"
  # Alert on-call
fi
```

---

### 3. LLM Server (vLLM)

**Critical Metrics**:

| Metric | Target | ⚠ Warning | ✗ Critical | Check Method |
|--------|--------|-----------|-----------|--------------|
| **Model Status** | Loaded | Reloading | Failed | `/v1/models` endpoint |
| **Token Rate** | 20+ tok/s | 15 tok/s | < 10 tok/s | Inference test |
| **Request Latency (p99)** | < 3s | < 5s | > 10s | Test with max_tokens=100 |
| **GPU Memory** | 21–22GB | < 23GB | > 24GB | `nvidia-smi` |
| **GPU Utilization** | 80%+ during load | 50%+ | < 20% | `nvidia-smi` |
| **Error Rate** | 0% | < 1% | > 5% | Log analysis |

**Log Locations**:
- Container logs: `docker-compose logs vllm -f`
- Model loading: `docker-compose logs vllm | grep -i "loaded\|loading"`
- Errors: `docker-compose logs vllm | grep -i error`

**Health Checks**:

```bash
# Check models available
curl -s http://vllm:8001/v1/models | python3 -m json.tool

# Test inference (quick response)
curl -X POST http://vllm:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "prompt": "Test",
    "max_tokens": 10
  }' | python3 -m json.tool

# Check GPU memory
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

**Monitoring Script** (run every 5 minutes):

```bash
#!/bin/bash
# Monitor vLLM health

# Check model loaded
MODELS=$(curl -s http://vllm:8001/v1/models | jq '.data[0].id // "error"')
if [ "$MODELS" != "Qwen/Qwen2.5-14B-Instruct-AWQ" ]; then
  echo "✗ Model not loaded: $MODELS"
  # Alert: Model failed to load
  exit 1
fi

# Check token rate (quick test)
START=$(date +%s%N)
curl -s -X POST http://vllm:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen2.5-14B-Instruct-AWQ","prompt":"AI","max_tokens":20}' \
  > /dev/null
END=$(date +%s%N)
LATENCY=$((($END - $START) / 1000000))  # Convert to milliseconds

if [ $LATENCY -gt 5000 ]; then
  echo "✗ vLLM slow: ${LATENCY}ms latency"
  # Alert: Slow inference
else
  echo "✓ vLLM healthy: ${LATENCY}ms latency"
fi
```

---

### 4. GPU Resources

**Critical Metrics**:

| Metric | Target | ⚠ Warning | ✗ Critical | Check Method |
|--------|--------|-----------|-----------|--------------|
| **GPU Memory Used** | 21GB | < 22.5GB | > 24GB | `nvidia-smi` |
| **GPU Utilization** | 80%+ under load | — | < 10% (idle should be 0%) | `nvidia-smi` |
| **GPU Temperature** | < 70°C | < 80°C | > 85°C | `nvidia-smi` |
| **Memory Errors** | 0 | — | > 0 | `nvidia-smi dmon` |
| **Power Consumption** | < 280W | < 320W | SHUTDOWN | `nvidia-smi` |

**Log Locations**:
- NVIDIA driver logs: `dmesg | grep -i nvidia`
- CUDA errors: Check application logs for CUDA errors

**GPU Health Checks**:

```bash
# Quick GPU status
nvidia-smi

# Memory details
nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv

# Temperature + power
nvidia-smi --query-gpu=index,temperature.gpu,power.draw --format=csv

# Monitor in real-time
nvidia-smi dmon -s pucvmet

# Test for errors
nvidia-smi -pm 1  # Enable persistence mode
nvidia-smi -pC 0,0,0  # Reset clocks to defaults
```

---

### 5. Application (Web App)

**Critical Metrics**:

| Metric | Target | ⚠ Warning | ✗ Critical | Check Method |
|--------|--------|-----------|-----------|--------------|
| **HTTP Status 200** | 99%+ | > 95% | < 90% | Endpoint health checks |
| **Response Latency (p99)** | < 500ms | < 1000ms | > 2000ms | Test requests |
| **Error Rate (5XX)** | 0% | < 0.5% | > 1% | Log analysis |
| **Memory Usage** | < 500MB | < 800MB | > 1.2GB | `docker stats app` |
| **CPU Usage** | 10–30% | 50% | > 80% | `docker stats app` |
| **Worker Count** | 2–4 | — | 0 (hung) | `ps aux \| grep uvicorn` |

**Log Locations**:
- Application logs: `docker-compose logs app -f`
- Errors: `docker-compose logs app | grep -i error`
- Uvicorn logs: Included in app logs

**Health Checks**:

```bash
# Quick app health
curl -s http://localhost:8000/health | python3 -m json.tool

# Get status
curl -v http://localhost:8000/health 2>&1 | grep "< HTTP"

# Check database connection within app
curl -s http://localhost:8000/api/status | python3 -m json.tool

# Monitor container resources
docker stats app --no-stream
```

---

## 📈 Metric Collection Intervals

**Recommended Collection Frequency**:

| Metric | Interval | Retention | Tool |
|--------|----------|-----------|------|
| GPU Memory, utilization | Every 10 seconds | 7 days | nvidia-smi + script |
| Database connections | Every 30 seconds | 30 days | MySQL query |
| HTTP response latency | Every minute | 90 days | Prometheus scrape |
| Service health (ping) | Every minute | 30 days | curl + script |
| Error rates | Every 5 minutes | 90 days | Log aggregation |
| Disk usage | Daily | 1 year | `df -h` |

---

## 🚨 Alerting Thresholds

### Alert Severity Levels

**Critical (Page On-Call Immediately)**:
- Database offline (0 connections for > 2 min)
- vLLM model not loaded (should be < 10 min from startup)
- GPU memory > 24GB for > 5 minutes
- App error rate > 2% for > 5 minutes
- Disk usage > 90%

**High (Email + Dashboard)**:
- Database connection count > 40 for > 10 minutes
- vLLM latency > 5s for > 5 consecutive requests
- ChromaDB health check failing > 30 seconds
- GPU temperature > 80°C for > 5 minutes
- App latency p99 > 2s for > 10 minutes
- Memory usage trending upward (> 10% increase in 1 hour)

**Medium (Dashboard + Log)**:
- Database slow queries increasing (> 10 per minute)
- ChromaDB response time > 500ms (average)
- GPU utilization low (< 20%) during active requests
- Disk usage > 75%
- Weekly service restarts as preventive maintenance

**Low (Log Only)**:
- Any warnings in service logs
- Configuration changes
- Routine maintenance tasks

---

## 📝 Logging Best Practices

### Log Levels for Each Service

**MariaDB**:
```sql
-- Enable slow query log
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL slow_query_log_file = '/var/log/mysql/slow-query.log';
SET GLOBAL long_query_time = 2;  -- Log queries taking > 2 seconds
```

**ChromaDB**:
```bash
# Logs are sent to stdout/stderr
# Configure in docker-compose.yaml:
# environment:
#   - CHROMA_LOG_LEVEL=INFO
```

**vLLM**:
```bash
# Logs are sent to stdout/stderr
# Can filter in docker-compose logs
docker-compose logs vllm | grep -E "INFO|ERROR"
```

**App**:
```python
# Django logging configured in settings
# Logs sent to stdout + rotating file logs
# Check: docker-compose logs app
```

### Log Retention Policy

| Log Type | Retention | Location |
|----------|-----------|----------|
| Application logs | 30 days | Docker logs (docker-compose logs) |
| Slow query logs | 7 days | MariaDB container `/var/log/mysql/` |
| GPU monitoring | 7 days | `/tmp/gpu_monitoring_*.csv` |
| Incident reports | 1 year | `/var/log/incidents/` |

---

## 📊 Dashboard Setup (Prometheus Optional)

### Key Metrics to Export (When Available)

```yaml
# Prometheus metrics to expose from app
- articles_ingested_total{status="success|error"}
- article_ingestion_duration_seconds (histogram)
- embeddings_generated_total
- embedding_generation_duration_seconds (histogram)
- inference_requests_total{model="..."}
- inference_duration_seconds (histogram)
- inference_tokens_generated_total
- gpu_memory_used_bytes
- gpu_memory_total_bytes
- db_connections_active
- db_query_duration_seconds (histogram)
- http_requests_total{status="2xx|4xx|5xx"}
- http_request_duration_seconds (histogram)
```

### Grafana Dashboard Panels (Example Queries)

**GPU Memory Tracking**:
```promql
gpu_memory_used_bytes{job="gpu"} / 1e9
```

**Database Connection Pool**:
```promql
db_connections_active{instance="mariadb:3306"}
```

**Inference Latency (p99)**:
```promql
histogram_quantile(0.99, inference_duration_seconds)
```

**Error Rate**:
```promql
rate(http_requests_total{status=~"5.."}[5m])
```

---

## 🔔 Notification Channels

### Configure Alerting To

**Slack** (for high/critical):
- Channel: #production-alerts
- Format: `[CRITICAL] vLLM model failed to load after 10 minutes`

**Email** (for high):
- To: ops-team@company.com
- Subject: `[ALERT] Database connections > 40`

**PagerDuty** (for critical):
- Trigger immediately
- Escalate if unacknowledged > 5 minutes

**Dashboard** (for all):
- Red/yellow/green indicators
- Historical trend lines

---

## 📋 Monitoring Checklist

**Daily**:
- [ ] Check GPU memory stable (< 22.5GB)
- [ ] Database connections < 30
- [ ] No errors in app logs
- [ ] vLLM inference latency < 3s

**Weekly**:
- [ ] Review error logs for patterns
- [ ] Check disk usage (< 75%)
- [ ] Verify backups completed
- [ ] Performance baselines stable (no regression)
- [ ] Plan any needed maintenance

**Monthly**:
- [ ] Review and update alerting thresholds
- [ ] Restart services for cleanup (1st of month)
- [ ] Update documentation
- [ ] Capacity planning review

**Quarterly**:
- [ ] Full disaster recovery test
- [ ] Security audit
- [ ] Performance optimization review
- [ ] Capacity expansion planning if needed

---

## 🎯 SLA Targets

| Metric | Target | |
|--------|--------|---|
| **Service Availability** | 99.9% (8.76 hr downtime/month) | ✓ |
| **Incident Response** | Critical alert acked in 5 min | ✓ |
| **MTTR (Mean Time To Resolve)** | < 15 min for standard issues | ✓ |
| **Backup Recovery Time** | < 1 hour to restore from backup | ✓ |
| **Database Query Latency (p99)** | < 100ms | ✓ |
| **Inference Latency** | < 3s per request | ✓ |
| **Embedding Latency** | < 200ms per document batch | ✓ |

---

## 📚 References

- [Service Operations Runbook](./SERVICE_OPERATIONS.md)
- [Service Dependencies](./.devcontainer/DEPENDENCIES.md)
- [Integration Tests](../tests/integration/README.md)
- [Performance Baselines](../docs/performance-baselines.md)

---

## 🆘 Quick Help

**Something broken?**
1. Run: `python .devcontainer/diagnostic.py`
2. Check: `docker-compose ps -a`
3. See: `docker-compose logs <service>`
4. Fix: See SERVICE_OPERATIONS.md recovery section
5. Escalate: If > 15 min unresolved, page on-call

**Questions?**
- See SERVICE_OPERATIONS.md troubleshooting decision tree
- Check logs for specific error messages
- Review incident reports for patterns

