# Service Operations Runbook

**Date**: February 8, 2026  
**Version**: 1.0  
**Audience**: Operations Engineers, DevOps, On-Call Support

---

## 📋 Quick Reference

**Emergency Contacts**:
- Database Issues: See [MariaDB Recovery](#mariadb-recovery)
- GPU/vLLM Issues: See [vLLM Emergency Recovery](#vllm-emergency-recovery)
- Vector DB Issues: See [ChromaDB Recovery](#chromadb-recovery)

**Quick Commands**:
```bash
# Check service status
docker compose ps -a

# View service logs
docker compose logs <service> -f

# Restart all services
docker compose restart

# Full restart (dangerous—breaks connections)
docker compose down && docker compose up -d
```

---

## 🔄 Service Restart Procedures

### Standard Restart (Graceful)

**When to use**: After configuration changes, memory cleanup, or weekly maintenance

```bash
# 1. Stop ingestion jobs (tell workers to stop accepting new jobs)
# 2. Wait for in-flight requests to complete (check health status)
# 3. Stop services in order

docker compose stop vllm      # Stop LLM server first (longest to restart)
docker compose stop chromadb  # Stop vector DB
docker compose stop app       # Stop web app
docker compose stop mariadb   # Stop database last

# 4. Verify all stopped
docker compose ps -a
# All should show Status: Exited

# 5. Start services in order
docker compose start mariadb  # Start database first
sleep 30                       # Wait for MariaDB to initialize
docker compose start chromadb # Start vector DB
sleep 10                       # Let ChromaDB initialize
docker compose start vllm      # Resume model loading (takes 2-5 min)
docker compose start app       # Start web app last

# 6. Verify all healthy
python .devcontainer/diagnostic.py
```

**Expected Timeline**:
- MariaDB: 10-30 seconds
- ChromaDB: 5-10 seconds  
- vLLM: 2-5 minutes (model download on first run)
- App: 5 seconds
- **Total**: 2.5-6 minutes

**Success Criteria**:
- All containers show `Status: Up`
- diagnostic.py shows all ✓ connected
- No error logs in `docker compose logs -f`

---

### Emergency Restart (Fast)

**When to use**: Service crash, memory exhaustion, response timeout > 60s

```bash
# Kill and restart specific service
docker compose restart <service>
# Examples:
# docker compose restart vllm
# docker compose restart chromadb
docker compose ps -a
docker compose logs <service> -f
docker compose restart
docker compose down && docker compose up -d
```bash
docker compose restart vllm
# Logs: Watch for "Qwen/Qwen2.5-14B-Instruct-AWQ loaded successfully"
docker compose logs vllm -f
```

docker compose stop vllm      # Stop LLM server first (longest to restart)
docker compose stop chromadb  # Stop vector DB
docker compose stop app       # Stop web app
docker compose stop mariadb   # Stop database last
docker compose logs chromadb -f
docker compose ps -a

**MariaDB** (relational database):
docker compose start mariadb  # Start database first
docker compose restart mariadb
# Logs: Watch for "mysqld: ready for connections"
docker compose logs mariadb -f
```

**App** (web application):
docker compose restart <service>
docker compose restart app
# Logs: Watch for "Uvicorn running on" or Django startup
docker compose logs app -f
```

---

### Full Service Reset (Nuclear Option)
docker compose logs > /tmp/logs_backup_$(date +%s).txt
**When to use**: Persistent corruption, failed restart, complete rebuild needed  
docker compose down

```bash
# 1. Notify users of maintenance window (required)
# 2. Save current state if needed
docker compose up -d

docker compose logs -f
docker compose down

# 4. Remove containers (but keep volumes for data persistence)
# DO NOT run: docker compose down -v
# (that would delete all data!)

# 5. If you need to reset specific volumes (rare):
docker volume rm <volume_name>
# Example: docker volume rm app_mariadb_data
# WARNING: This deletes all data in that volume!
**Docker status** (`docker compose ps -a`):
# 6. Start fresh
docker compose up -d
python .devcontainer/diagnostic.py
```

**Expected Timeline**: 3-7 minutes total

**Recovery Checklist**:
- [ ] All containers running (`docker compose ps -a`)
- [ ] All services ✓ connected (diagnostic.py output)
- [ ] No errors in logs (`docker compose logs | grep -i error`)
- [ ] Database migrations applied (check logs for "Applied")
- [ ] Users notified of recovery completion

---

## 🚨 Emergency Recovery

### MariaDB Recovery

**Symptom**: "Can't connect to MySQL server", ingestion failures

```bash
# 1. Check service status
docker compose ps mariadb
# Should show: Status: Up

# 2. Check logs for errors
docker compose logs mariadb | tail -50

# 3. Verify port is open
python3 -c "import socket; sock = socket.create_connection(('mariadb', 3306), timeout=5); sock.close(); print('✓ Port open')"

# 4. Check database connectivity
docker compose exec app python manage.py shell << 'EOF'
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
    print("✓ Database responsive")
EOF

# 5. If stuck, restart
docker compose restart mariadb
sleep 30
python .devcontainer/diagnostic.py
```

**Common Issues & Fixes**:

| Issue | Symptom | Fix |
|-------|---------|-----|
| **Out of Memory** | Process killed, container exits | `docker compose restart mariadb` |
| **Connection Pool Exhausted** | "1040 Too many connections" | Check for zombie connections, restart app |
| **Disk Full** | Inserts fail, grow operations slow | Check `/var/lib/mysql` space, cleanup old logs |
| **Crash on Startup** | Immediately exits after restart | Check logs: `docker compose logs mariadb -f` |

**Emergency Connection Drop Recovery**:
```bash
# If app can't connect to MariaDB midway:

# 1. Check MariaDB is still running
docker compose ps mariadb  # Must show "Up"

# 2. Restart just the app (reconnect)
docker compose restart app

# 3. Monitor recovery
docker compose logs app -f | grep -i "database\|connect"
```

---

### ChromaDB Recovery

**Symptom**: "Connection refused", 404 errors on `/api/`, embeddings fail

```bash
# 1. Check service health
curl -s http://chromadb:3307/api/v1/heartbeat | python3 -m json.tool

# 2. Check logs
docker compose logs chromadb | tail -30

# 3. If port unavailable, restart
docker compose restart chromadb

# 4. Wait for startup
sleep 10

# 5. Retry health check
curl -s http://chromadb:3307/api/v1/heartbeat
# Should return: {"status":"ok"}
```

**Common Issues & Fixes**:

| Issue | Symptom | Fix |
|-------|---------|-----|
| **API Version Mismatch** | 404 on all endpoints | Verify version: `docker compose logs chromadb \| grep Chroma` |
| **Database Locked** | Slow queries, timeouts | Let running operations complete (2-5 min), then restart if needed |
| **Memory Leak** | Gradual slowdown, eventual crash | Restart: `docker compose restart chromadb` (monitor weekly) |
| **Collections Corrupted** | Errors on specific collections | Delete & recreate collection (data loss for that collection) |

**Manual Collection Recovery** (if needed):
```bash
# Connect to ChromaDB container
docker compose exec chromadb bash

# Inside container, check collections
chroma_cli --path /data list_collections

# Or via HTTP API
curl -s http://localhost:8000/api/v1/collections | python3 -m json.tool

# If stuck, exit container and restart
exit
docker compose restart chromadb
```

---

### vLLM Emergency Recovery

**Symptom**: Model stuck loading, inference timeout, GPU memory exhausted

```bash
# 1. Check if running
docker compose ps vllm  # Should show "Up"

# 2. Check GPU memory
nvidia-smi
# vllm container should show ~21-22GB used (normal)

# 3. Check if model loaded
curl -s http://vllm:8001/v1/models | python3 -m json.tool
# Should show: "Qwen/Qwen2.5-14B-Instruct-AWQ" in models list

# 4. If stuck on startup (loading)
docker compose logs vllm -f
# Watch for: "Qwen ... loaded successfully" (takes 2-5 min first time)
# If > 10 min, interrupt and restart

# 5. Hard restart (frees GPU memory)
docker compose stop vllm
sleep 5
nvidia-smi  # Should show vllm container gone
docker compose start vllm
sleep 60    # Wait for model reload
nvidia-smi  # Should show vllm using GPU again
```

**Common Issues & Fixes**:

| Issue | Symptom | Fix |
|-------|---------|-----|
| **Out of GPU Memory** | CUDA out of memory, inference fails | Restart service (frees GPU), don't run concurrent requests |
| **HuggingFace Network Timeout** | Model download fails, stuck for > 5 min | Restart: `docker compose restart vllm` (retry download) |
| **Inference Response Timeout** | Requests hang > 60s | Model may be overloaded; throttle concurrent requests |
| **Model Not Loaded** | `/v1/models` returns empty | Wait 2-5 min, check logs: `docker compose logs vllm -f` |

**Manual Inference Test** (verify working):
```bash
curl -X POST http://vllm:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "prompt": "What is AI?",
    "max_tokens": 50
  }' | python3 -m json.tool
```

Expected response:
```json
{
  "id": "cmpl-...",
  "choices": [
    {
      "text": "AI stands for Artificial Intelligence. It refers to...",
      "index": 0
    }
  ]
}
```

---

### GPU Memory Exhaustion Recovery

**Symptom**: "CUDA out of memory", inference requests fail

```bash
# 1. Check current GPU memory
nvidia-smi

# 2. See what's using memory
nvidia-smi -l 1  # Sample every 1 second

# 3. If vllm using > 23GB (DANGER near limit)
docker compose restart vllm

# 4. Verify recovery
sleep 60
nvidia-smi
# Should show vllm using ~21GB (normal)

# 5. Monitor for memory leaks (weekly)
watch -n 5 nvidia-smi
# Look for gradual increase → indicates memory leak
```

**Prevention**:
- Don't run concurrent inference requests (vLLM doesn't queue, just fails)
- Monitor GPU memory weekly
- Restart vllm monthly for maintenance
- Alert if GPU memory > 23.5GB for > 5 minutes

---

## 📊 Health Check Interpretation

### Service Status Meanings

**Docker status** (`docker compose ps -a`):

```
Status: Up X minutes       → ✓ Service running, healthy
Status: Up (unhealthy)     → ⚠ Service running but health check failing
Status: Exited (0)         → ℹ Service stopped cleanly
Status: Exited (137)       → ⚠ Service killed (out of memory or manual kill)
Status: Exited (139)       → ⚠ Service killed (segmentation fault)
Status: Exited (1)         → ✗ Service crashed with error
```

### Diagnostic Output Interpretation

**Green ✓ (All healthy)**:
```
✓ MariaDB      → connected
✓ ChromaDB     → connected
✓ vLLM         → connected
```
Action: Ready for operations, all systems nominal

**Yellow ⚠ (Degraded but recovering)**:
```
✓ MariaDB      → connected
✗ ChromaDB     → refused
⚠ vLLM         → may still be loading
```
Action: Wait 30-60 seconds, retry diagnostics; services may be initializing

**Red ✗ (Critical failure)**:
```
✗ MariaDB      → refused
✗ ChromaDB     → refused
✗ vLLM         → refused
```
Action: Check `docker compose ps -a`, restart failed services

### Log Interpretation

**Normal startup sequence** (check logs):
```
mariadb:     "mysqld: ready for connections"
chromadb:    "Chroma server: ... Listening on ..."
vllm:        "Qwen/Qwen2.5-14B-Instruct-AWQ loaded successfully"
app:         "Uvicorn running on http://0.0.0.0:8000"
```

**Warning signs** (take action):
```
"Out of memory"              → Restart that service
"Too many connections"       → Restart app (reconnect)
"CUDA out of memory"         → Restart vllm (free GPU)
"Connection refused"         → Service crashed, restart needed
"timeout"                    → Service slow/stuck, consider restart
"panic" / "fatal"            → Critical error, investigate logs
```

---

## 🔍 Troubleshooting Decision Tree

```
┌─ Service not responding?
│  ├─ Check: docker compose ps -a
│  │  ├─ Status: Exited → Restart: docker compose restart <service>
│  │  ├─ Status: Up (unhealthy) → Check logs: docker compose logs <service>
│  │  └─ Status: Up → Check port open manually, see service section above
│  │
│  └─ After restart, still failing?
│     ├─ Check logs for errors: docker compose logs <service> | grep -i "error\|fatal"
│     ├─ If "out of memory" → Increase container memory limit
│     ├─ If network error → Check docker network: docker network inspect bridge
│     └─ If unknown → Full restart: docker compose down && docker compose up -d

├─ Database ingestion slow?
│  ├─ Check: SELECT COUNT(*) FROM articles; 
│  ├─ Check MariaDB connections: SHOW PROCESSLIST;
│  │  ├─ > 50 connections → Kill idle: KILL xxx;
│  │  └─ < 50 → Database OK, upstream issue
│  └─ Restart app: docker compose restart app (reconnect to pool)

├─ Embeddings taking too long?
│  ├─ Check ChromaDB: curl http://chromadb:3307/api/v1/heartbeat
│  │  ├─ 404/timeout → Restart: docker compose restart chromadb
│  │  ├─ 200 OK → Service fine, check network latency
│  │  └─ Refused → Service down, restart container
│  └─ Check collection size: May be slow with 100K+ embeddings

├─ Inference requests timing out?
│  ├─ Check: curl http://vllm:8001/v1/models
│  │  ├─ Timeout → Model still loading, wait 2-5 min
│  │  ├─ Empty list → Model failed to load, check logs
│  │  └─ Lists model → Service OK, check request payload
│  ├─ Check GPU memory: nvidia-smi
│  │  ├─ > 23GB → Restart: docker compose restart vllm
│  │  └─ < 23GB → Service fine, may be overloaded
│  └─ Too many concurrent requests → Queue or retry later

└─ Memory/CPU spike?
   ├─ Check what changed (new deployment, new query type)
   ├─ Monitor: docker stats
   ├─ If persistent → Analysis + optimization needed
   └─ If temporary spike → Normal, monitor for patterns
```

---

## 📋 Pre-Deployment Checklist

**Before going live with changes**:

- [ ] All containers running: `docker compose ps -a` shows all "Up"
- [ ] All services healthy: `python .devcontainer/diagnostic.py` shows all ✓
- [ ] Database accessible: `docker compose exec app python manage.py shell` (test query)
- [ ] No errors in logs: `docker compose logs --tail=20` (last 50 lines clean)
- [ ] Model loaded: `curl http://vllm:8001/v1/models` returns Qwen model
- [ ] Test basic flow: Ingestion → Embedding → Query pipeline works
- [ ] GPU memory normal: `nvidia-smi` shows vllm ~21GB (not overloaded)
- [ ] Backup current state: `docker compose logs > /tmp/backup_logs.txt`

**Go/No-Go Decision**:
- ✅ All checks pass → GREEN: Ready for deployment
- ⚠️ 1-2 warnings → YELLOW: Proceed with caution, monitor closely
- ✗ 3+ failures → RED: Do not deploy, resolve issues first

---

## 📝 Incident Response Template

**When an incident occurs**:

```
INCIDENT REPORT
───────────────

Time Detected:    [HH:MM UTC]
Service Affected: [Service name]
Severity:         [Critical/High/Medium/Low]

Symptoms:
[What users/apps reported]

Investigation:
[Command output, logs, metrics]

Root Cause:
[What was actually failing]

Resolution:
[What you did to fix it]

Prevention:
[What we'll do to prevent recurrence]

Timeline:
- HH:MM - Issue detected
- HH:MM - Root cause identified  
- HH:MM - Fix applied
- HH:MM - Verified resolved

Owner (who handled):
```

**When to escalate**:
- Issue not resolved in 15 minutes
- Multiple services failing simultaneously
- Data loss or corruption risk
- Unable to restore within RTO
- Contact on-call engineer

---

## 🔐 Security Notes

**Password Management**:
- Never use plaintext passwords in docker-compose.yaml
- All secrets in `/app/global.env` (git-ignored)
- Production: Use Vault integration (see docs/operations/VAULT_SETUP.md)

**Network Access Control**:
- MariaDB: Only accessible from app container (port 3306 not exposed)
- ChromaDB: Only accessible from app/vllm containers (port 3307 not exposed)
- vLLM: Only accessible from app container (port 8001 not exposed)
- All inter-service communication via Docker internal network

**Backup Strategy**:
- Docker volumes persist even if container stops
- Daily backup of MariaDB: `docker compose exec mariadb mysqldump --all-databases > /backup/db_$(date +%Y-%m-%d).sql`
- Weekly backup of ChromaDB vector store
- Keep 30 days of backups minimum

---

## 📞 Support Contacts

- **Database Admin**: See MARIADB_CONTACT in production config
- **ML Ops**: See VLLM_CONTACT in production config
- **On-Call**: Rotate on-call schedule (see docs/operations/ON_CALL.md)
- **Escalation**: Contact Engineering Lead if unresolved after 30 minutes

---

## References

- [Service Dependencies](./.devcontainer/DEPENDENCIES.md)
- [Service Startup Guide](./.devcontainer/SERVICE_STARTUP.md)
- [Monitoring Setup](./MONITORING.md) (see next section)
- [Operations Checklist](./.devcontainer/services-operational-checklist.md)

