# Phase 3: Operational Runbooks - Quick Reference

**Date**: February 8, 2026  
**Status**: Phase 3 Complete (Operational Documentation)

---

## 📚 Quick Navigation

### Documentation Files

| File | Purpose | Read Time |
|------|---------|-----------|
| [SERVICE_OPERATIONS.md](./docs/operations/SERVICE_OPERATIONS.md) | Step-by-step restart procedures, emergency recovery | 10 min |
| [MONITORING.md](./docs/operations/MONITORING.md) | Key metrics, alerting thresholds, logging setup | 8 min |
| [docker-compose.yaml](./devcontainer/docker-compose.yaml) | Service definitions with labels & metadata | 5 min |
| [SERVICE_STARTUP.md](./.devcontainer/SERVICE_STARTUP.md) | Per-service startup behavior & common issues | 8 min |
| [DEPENDENCIES.md](./.devcontainer/DEPENDENCIES.md) | Service dependency graph & startup order | 5 min |

---

## 🚨 Emergency Response

**Something broken?** Follow this decision tree:

```bash
# Step 1: Check status
docker compose ps -a

# Step 2: Get details
python .devcontainer/diagnostic.py

# Step 3: Based on symptom, see:
# - Database issue     → SERVICE_OPERATIONS.md #mariadb-recovery
# - ChromaDB issue     → SERVICE_OPERATIONS.md #chromadb-recovery
# - vLLM issue         → SERVICE_OPERATIONS.md #vllm-emergency-recovery
# - GPU issue          → SERVICE_OPERATIONS.md #gpu-memory-exhaustion-recovery
```

**If >= 15 minutes unresolved**:
- Page on-call engineer
- Open incident (see incident template)
- Save logs: `docker compose logs > /tmp/incident_logs.txt`

---

## 🔄 Common Operations

### Restart Single Service
```bash
docker compose restart chromadb    # Restart specific service
docker compose logs chromadb -f    # Watch restart
```

### Graceful Restart All Services
```bash
docker compose stop vllm chromadb app mariadb
sleep 10  # Wait for shutdown
docker compose start mariadb
sleep 30  # MariaDB initialization
docker compose start chromadb  
sleep 10
docker compose start vllm
sleep 120  # Wait for model load
docker compose start app
# Verify: python .devcontainer/diagnostic.py
```

### View Logs
```bash
docker compose logs mariadb | grep -i error       # Specific service
docker compose logs -f vllm                        # Follow logs
docker compose logs >> /tmp/all_logs.txt           # Save to file
```

### Check Resource Usage
```bash
docker stats                                       # All containers
nvidia-smi                                        # GPU details
docker exec mariadb mysql -u root -p -e "SHOW STATUS LIKE 'Threads_connected';"
```

---

## 📊 Key Metrics to Monitor

### Daily Checks (5 minutes)

```bash
# 1. GPU Memory
nvidia-smi | grep vllm
# Should show: ~21-22GB used (NORMAL)
# Alert if: > 23.5GB for > 5 minutes

# 2. Database Connections  
docker exec mariadb mysql -u root -p -e "SHOW STATUS LIKE 'Threads_connected';"
# Should show: < 30 connections
# Alert if: > 50 connections

# 3. Service Health
curl -s http://localhost:8000/health
# Should return: 200 OK with health details
# Alert if: != 200 or no response

# 4. vLLM Model
curl -s http://vllm:8001/v1/models | jq '.data[0].id'
# Should show: "Qwen/Qwen2.5-14B-Instruct-AWQ"
# Alert if: Empty, error, or different model
```

### Weekly Tasks (30 minutes)

- [ ] Review error logs: `docker compose logs --since 24h | grep -i error`
- [ ] Check disk usage: `df -h` (alert if > 75%)
- [ ] Verify backups completed (if configured)
- [ ] Check for memory leaks (GPU usage trending upward)
- [ ] Review incident reports
- [ ] Update alerting thresholds if needed

---

## 🎯 Service Startup Order & Timeline

**Expected sequence**:

```
Time    Service       Status              Action
────────────────────────────────────────────────────────
 0s     mariadb       Starting...         Wait 30s for init
30s     chromadb      Starting...         Wait 10s for init
40s     vllm          Starting...         Wait 2-5 min for model load
40s     app           Ready to start      Start after vllm loads
300s    vllm          Ready               Model loaded, app can start
305s    app           Running             All services healthy
```

**Total time**: ~5 minutes (first startup longer if model needs download)

---

## 💾 Service Dependencies

**Startup order** (strict):
1. **mariadb** ← Foundation (app depends on this)
2. **chromadb** ← Works independently
3. **vllm** ← Loads model (takes time)
4. **app** ← Depends on all above

**Shutdown order** (reverse):
1. **app** ← Stop first
2. **vllm** ← Stop GPU services
3. **chromadb** ← Stop supporting services
4. **mariadb** ← Stop database last

---

## 🏷️ Service Labels (docker-compose)

Each service now has metadata labels. View with:

```bash
# View labels for all services
docker compose ps --format 'table {{.Service}}\t{{.Labels}}'

# Or in raw docker-compose.yaml
cat docker-compose.yaml | grep -A 20 "labels:"
```

**Key labels**:
- `tier`: critical/high/low → Restart priority
- `gpu_required`: true/false → Resource needs
- `healthcheck`: command → How to verify health
- `dependencies`: services → What it needs
- `restart_policy`: always/on-failure/no

---

## 🚨 Alert Thresholds (From MONITORING.md)

### Critical Alerts (Page On-Call)

- Database offline for > 2 minutes
- vLLM model not loaded after 10 minutes
- GPU memory > 24GB for > 5 minutes
- App error rate > 2% for > 5 minutes
- Disk usage > 90%

### High Alerts (Email + Dashboard)

- Database connections > 40 for > 10 minutes
- vLLM latency > 5s consistently
- ChromaDB health check failing > 30 seconds
- GPU temperature > 80°C for > 5 minutes
- Memory usage trending up (> 10% in 1 hour)

### Medium Alerts (Dashboard + Log)

- Slow queries increasing (> 10/min)
- ChromaDB latency > 500ms average
- GPU utilization low (< 20%) during requests
- Disk usage > 75%

---

## 📋 Pre-Deployment Checklist

Before rolling out changes:

```bash
□ All containers running
  docker compose ps -a | grep "Up"

□ All services healthy
  python .devcontainer/diagnostic.py
  # All should show ✓

□ No errors in logs
  docker compose logs --since 1h | grep -ic error
  # Should return: 0

□ Database accessible
  docker exec app python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute('SELECT 1')"

□ Model loaded
  curl -s http://vllm:8001/v1/models | jq '.data | length'
  # Should be: 1 (at least one model)

□ GPU memory normal
  nvidia-smi | grep vllm | awk '{print $11}'
  # Should be: ~21GB (not > 23GB)

□ Test basic pipeline
  # Run: python tests/integration/test_devcontainer.py
  # Should show: 5/5 passing (or 4/5 if services not all ready)
```

---

## 📞 Escalation Process

**If issue >= 15 minutes unresolved**:

1. **Gather information**:
   ```bash
  docker compose ps -a > /tmp/status.txt
  docker compose logs > /tmp/logs.txt
   nvidia-smi > /tmp/gpu.txt
   ```

2. **Page on-call engineer** (see incident template)

3. **Document**:
   - What happened
   - When it started
   - Steps already taken
   - Current status

4. **Incident report** (afterward):
   - Root cause analysis
   - Permanent fix
   - Prevention for future

---

## 🔗 Cross-References

**Need detailed procedure?**
→ See [SERVICE_OPERATIONS.md](./docs/operations/SERVICE_OPERATIONS.md)

**Need monitoring setup?**
→ See [MONITORING.md](./docs/operations/MONITORING.md)

**Need service info?**
→ See [DEPENDENCIES.md](./.devcontainer/DEPENDENCIES.md)

**Need startup troubleshooting?**
→ See [SERVICE_STARTUP.md](./.devcontainer/SERVICE_STARTUP.md)

**Need to run tests?**
→ See [tests/integration/README.md](./tests/integration/README.md)

---

## ✅ Phase 3 Completion

**Deliverables**:
- ✅ SERVICE_OPERATIONS.md (530+ lines of procedures)
- ✅ MONITORING.md (420+ lines of metrics & alerts)
- ✅ docker-compose.yaml enhanced with labels
- ✅ Quick reference card (this document)

**Total Phase 3**: ~1000 lines of operational documentation

**Key outcomes**:
- Operators can restart services without developer intervention
- Clear escalation paths for urgent issues
- Monitoring setup with alerting thresholds
- Service dependencies documented
- Emergency recovery procedures step-by-step

---

## 🎬 Next Steps (Phase 4)

**Phase 4: Production Readiness** will focus on:
1. Systemd deployment validation
2. Vault secrets integration
3. Security audit
4. Production configuration generation
5. Disaster recovery testing

---

**Phase 3 Status**: ✅ COMPLETE - Operational runbooks ready for team

