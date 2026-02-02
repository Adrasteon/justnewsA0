---
title: "Operator Quick Start Guide"
description: "Daily operations reference for JustNews startup, shutdown, common scenarios, troubleshooting, and health checks"
tags: ["operations", "startup", "troubleshooting", "quick-reference"]
status: "current"
version: "1.0"
last_updated: "2026-02-02"
audience: ["operators", "devops"]
canonical_script: "infrastructure/systemd/canonical_system_startup.sh"
---

# JustNews Canonical Startup - Operator Quick Guide

**Last Updated:** February 2, 2026  
**Script Location:** `infrastructure/systemd/canonical_system_startup.sh`

---

## Quick Start

### Basic Full Startup
```bash
cd /home/adra/justnewsA0
sudo infrastructure/systemd/canonical_system_startup.sh
```
**Expected Duration:** 3-5 minutes  
**What Happens:** All 5 phases execute automatically

### Full Shutdown
```bash
sudo infrastructure/systemd/canonical_system_startup.sh stop
```
**Expected Duration:** 30-60 seconds  
**What Happens:** Cleans GPU, releases ports, stops all services

---

## Common Scenarios

### Scenario 1: Cold-Start (First Boot of the Day)
```bash
sudo infrastructure/systemd/canonical_system_startup.sh
```
- Phase 1: Environment check (should be instant)
- Phase 2: Service restart (30s, GPU power limit applied)
- Phase 3: Django migrations (check DB schema)
- Phase 4: Chroma bootstrap (creates vector collections)
- Phase 5: GPU warmup (2-3 minutes on first load)
- **Total Time:** 5-7 minutes

### Scenario 2: Hot-Restart (System Already Running)
```bash
sudo infrastructure/systemd/canonical_system_startup.sh
```
- Phase 1: Instant (already validated)
- Phase 2: Fast (services mostly restarted)
- Phase 3: Instant (migrations already current)
- Phase 4: Instant (collections already exist)
- Phase 5a: Fast (GPU models cached in memory)
- **Total Time:** 1-2 minutes

### Scenario 3: Verify Status Without Restarting
```bash
infrastructure/systemd/canonical_system_startup.sh --dry-run
```
**What You'll See:** All commands printed but NO changes made  
**Use Case:** Debug startup logic without affecting running system

### Scenario 4: Emergency Restart (Git Rollback or Corruption)
```bash
sudo infrastructure/systemd/canonical_system_startup.sh
```
(Same as cold-start - full reset happens automatically)

### Scenario 5: Suspect Database Schema Issues
```bash
sudo infrastructure/systemd/canonical_system_startup.sh --skip-migrations
```
⚠️ **WARNING:** Only use if you KNOW schema is current (e.g., just ran migrations manually)

### Scenario 6: Port Conflicts?
```bash
sudo infrastructure/systemd/canonical_system_startup.sh stop
# Wait 5 seconds, then:
sudo infrastructure/systemd/canonical_system_startup.sh
```
The full stop→start cycle properly releases all ports.

### Scenario 7: Check Without Smoke Tests (Debug Config Issues)
```bash
sudo infrastructure/systemd/canonical_system_startup.sh --skip-smoke-tests
```

---

## What Each Phase Does

| Phase | ⏱ Time | Purpose | Can Skip? | Critical? |
|-------|--------|---------|-----------|-----------|
| 1️⃣ Prerequisites | ~10s | Verify MariaDB, ChromaDB running | ❌ No | ✅ YES |
| 2️⃣ Services | ~30s | Restart all 17 agents + observability | ❌ No | ✅ YES |
| 3️⃣ Migrations | ~5-30s | Update database schema | ⚠️ --skip-migrations | ✅ YES |
| 4️⃣ Chroma | ~5s | Create vector collections | ⚠️ --skip-chroma-bootstrap | ❌ No |
| 5️⃣ vLLM Ready | ~60-180s | Wait for GPU models to load | ❌ No | ❌ No (background-OK) |
| 5️⃣ Health Check | ~10s | Verify all service ports | ❌ No | ❌ No |
| 5️⃣ Smoke Tests | ~30s | Test HTTP endpoints | ⚠️ --skip-smoke-tests | ❌ No |

---

## Interpreting Output

### Success

```
[INFO] [PHASE 1/5] Checking prerequisites...
✓ [SUCCESS] MariaDB connectivity verified
✓ [SUCCESS] ChromaDB connectivity verified

[INFO] [PHASE 2/5] Restarting JustNews systemd services...
✓ [SUCCESS] gpu_orchestrator started (port 8014)
✓ [SUCCESS] mcp_bus started (port 8000)
... (other services)

[INFO] [PHASE 3/5] Executing Django migrations...
✓ [SUCCESS] Django migrations applied

[INFO] [PHASE 4/5] Bootstrapping Chroma...
✓ [SUCCESS] Chroma collections verified

[INFO] [PHASE 5a/5] Waiting for vLLM readiness...
✓ [SUCCESS] vLLM ready in 45 seconds

[INFO] [PHASE 5b/5] Running health summary...
✓ [SUCCESS] All 18 services healthy

[INFO] [PHASE 5c/5] Running integration smoke tests...
✓ [SUCCESS] All endpoints responsive

✅ STARTUP COMPLETE - JustNews ready for work
```

### Phase Failure Example

```
[ERROR] [PHASE 2/5] Service restart failed
[ERROR] Could not enable justnews@gpu_orchestrator.service
[ERROR] Check systemd logs: journalctl -u justnews@gpu_orchestrator -n 50

STARTUP ABORTED
Actions: 
  1) Review error above
  2) Check port 8014: sudo lsof -i :8014
  3) Manual fix or escalate
```

---

## Troubleshooting

### Port Already in Use
```bash
# Find what's using port 8000 (example)
sudo lsof -i :8000

# Kill it
sudo kill -9 <PID>

# Or do full shutdown first
sudo infrastructure/systemd/canonical_system_startup.sh stop
```

### Database Connection Fail
```bash
# Check MariaDB
sudo systemctl status mariadb

# Start it if down
sudo systemctl start mariadb

# Try again
sudo infrastructure/systemd/canonical_system_startup.sh
```

### Chroma Bootstrap Error
```bash
# This is non-fatal, but check Chroma status
sudo systemctl status justnews-chroma  # or however it's named

# Should continue anyway; watch for embedding errors later
```

### vLLM Timeout (GPU Still Loading)
```bash
# This is NORMAL on cold boot
# GPU models take 2-3 minutes to load
# Don't interrupt - let it run

# If it times out after 180s, check:
nvidia-smi  # Is GPU memory being used?
journalctl -u justnews@gpu_orchestrator -n 50  # Any errors?
```

### Smoke Test Failures
```bash
# These are non-fatal but indicate config issues
# Check the failing endpoint:
curl -v http://localhost:8000/health  # Example

# Or manually run test script
bash infrastructure/systemd/helpers/boot_smoke_test.sh
```

---

## Advanced Options

### Show Help
```bash
infrastructure/systemd/canonical_system_startup.sh --help
```

### Dry-Run Test
```bash
sudo infrastructure/systemd/canonical_system_startup.sh --dry-run
```
Prints all commands that WOULD run without actually running them.

### Pass Options to reset_and_start.sh
```bash
sudo infrastructure/systemd/canonical_system_startup.sh --safe-mode on
# Forwards --safe-mode to reset_and_start.sh
```

### Verbose Logging
```bash
# Check the script's DEBUG flag (edit if needed)
VERBOSE=1 sudo infrastructure/systemd/canonical_system_startup.sh
```

---

## Health Checks (Manual)

After startup completes, verify yourself:

```bash
# 1. Check all systemd services are active
sudo systemctl list-units 'justnews*' | grep active

# 2. Check key ports
curl http://localhost:8000/health  # MCP Bus
curl http://localhost:8001/health  # Chief Editor
curl http://localhost:8014/health  # GPU Orchestrator

# 3. Check GPU
nvidia-smi  # Should show vLLM model loaded

# 4. Check Prometheus
curl http://localhost:9090/api/v1/status/buildinfo

# 5. Check Grafana
curl http://localhost:3000/api/health
```

---

## Maintenance

### Override Migrations (Advanced)
```bash
cd /home/adra/justnewsA0
python manage.py showmigrations  # List all migrations
python apply_migrations_script.py  # Run manually
```

### Clear & Rebench Vector Store
```bash
# On next startup, Chroma will auto-bootstrap
# To force re-bootstrap:
# 1. Stop system
sudo infrastructure/systemd/canonical_system_startup.sh stop

# 2. Delete Chroma data (if local file-based)
# rm -rf /path/to/chroma/data

# 3. Start again
sudo infrastructure/systemd/canonical_system_startup.sh
```

### Check Individual Service Logs
```bash
# Last 50 lines of GPU orchestrator
journalctl -u justnews@gpu_orchestrator -n 50

# All failures
journalctl -u justnews@gpu_orchestrator -p err

# Follow live
journalctl -u justnews@gpu_orchestrator -f
```

---

## Best Practices

1. **Always use `canonical_system_startup.sh`** - It's the single source of truth
2. **Don't mix manual starts** - Let the script orchestrate everything
3. **Use `--dry-run` first** if unsure - Test before applying changes
4. **Check logs if Phase N fails** - Script output tells you which phase and why
5. **Wait for Phase 5 completion** - Don't send requests before "STARTUP COMPLETE"
6. **Use `stop` before changes** - Full shutdown ensures clean state
7. **Monitor GPU during startup** - `nvidia-smi` shows warmup progress

---

## Performance Expectations

### Startup Timeline
```
Cold Boot (First Start Today)
├─ Phase 1: 10s (env validation)
├─ Phase 2: 30s (service init)
├─ Phase 3: 20s (migrations)
├─ Phase 4: 5s (chroma)
├─ Phase 5: 180s (GPU warmup)
└─ TOTAL: 245s (~4 minutes)

Warm Boot (System Already Running)
├─ Phase 1: 2s (cached)
├─ Phase 2: 15s (fast restart)
├─ Phase 3: 2s (no changes)
├─ Phase 4: 1s (cached)
├─ Phase 5: 30s (models in memory)
└─ TOTAL: 50s (~1 minute)
```

### Resource Usage During Startup
- **CPU:** Spikes to 80-90% during Phase 2 (service init)
- **RAM:** ~8GB steady-state, +2-3GB during Phase 3 (migrations)
- **GPU:** Cold → 80% utilization ramp during Phase 5 (model loading)
- **Disk:** ~500MB/s during Phase 3 (migrations and bootstrap)

---

## Support

**Issues with startup?**

1. Check [`CANONICAL_STARTUP_ANALYSIS.md`](./CANONICAL_STARTUP_ANALYSIS.md) - Detailed technical analysis
2. Review script output - Phase and error messages are clear
3. Check individual service logs - `journalctl -u justnews@SERVICE_NAME`
4. Try `--dry-run` - See what would happen without risk

**Script location for editing:**
```
/home/adra/justnewsA0/infrastructure/systemd/canonical_system_startup.sh
```

---

**Version:** 1.0 (Enhanced with 5-phase system)  
**Status:** Production Ready ✅  
**Commit:** 07ceb63
