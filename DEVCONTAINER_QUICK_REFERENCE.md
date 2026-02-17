# DevContainer Issues - QUICK REFERENCE CARD

## 🎯 TL;DR: Issues Found

| # | Issue | Severity | Fix Time | Status |
|---|-------|----------|----------|--------|
| 1 | Journalist agent port hardcoded to 8016 (conflicts with Crawler Control) | 🔴 CRITICAL | 5 min | Not Fixed |
| 2 | Missing 18+ agent port environment variables in global.env | 🟡 MEDIUM | 5 min | Not Fixed |
| 3 | HITL service naming inconsistency (dual naming convention) | 🟡 LOW | 5 min | Optional |

**Total Fix Time: ~10-15 minutes** | **Complexity: Easy** | **Risk: Low**

---

## 📍 Where to Fix

### Fix #1: agents/journalist/main.py (Line 97)

**BEFORE:**
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8016)
```

**AFTER:**
```python
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("JOURNALIST_PORT", 8017))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

---

### Fix #2: global.env (End of File)

**ADD THIS SECTION:**
```bash
# ==============================================================================
# Agent Service Ports
# ==============================================================================
MCP_BUS_PORT=8000
CHIEF_EDITOR_AGENT_PORT=8001
SCOUT_AGENT_PORT=8002
FACT_CHECKER_AGENT_PORT=8018
FACT_CHECKER_EXTERNAL_URL=http://localhost:8003
ANALYST_AGENT_PORT=8004
SYNTHESIZER_AGENT_PORT=8005
CRITIC_AGENT_PORT=8006
MEMORY_AGENT_PORT=8007
REASONING_AGENT_PORT=8008
NEWSREADER_PORT=8009
ANALYTICS_AGENT_PORT=8012
ARCHIVE_AGENT_PORT=8012
DASHBOARD_PORT=8013
GPU_ORCHESTRATOR_PORT=8014
CRAWLER_AGENT_PORT=8015
CRAWLER_CONTROL_AGENT_PORT=8016
JOURNALIST_PORT=8017
AUTH_SERVICE_PORT=8018
HITL_SERVICE_PORT=8019
WORKFLOW_ORCHESTRATOR_PORT=8020
MCP_BUS_MISSING_AGENT_POLL_INTERVAL_SEC=30

# Service URLs
MCP_BUS_URL=http://localhost:8000
VLLM_BASE_URL=http://vllm:8001/v1
```

---

### Fix #3: agents/hitl_service/main.py (Line 30) — OPTIONAL

**BEFORE:**
```python
port = int(os.environ.get("HITL_SERVICE_PORT", default_value))
```

**AFTER:**
```python
# Supports both HITL_SERVICE_PORT (new) and HITL_PORT (legacy)
port = int(os.environ.get("HITL_SERVICE_PORT", 
           os.environ.get("HITL_PORT", 8019)))
```

---

## 🚀 Quick Verification

```bash
# After fixes, test everything works:

# 1. Rebuild container
docker compose down && docker compose build && docker compose up -d

# 2. Check initialization
docker compose logs app | grep SUCCESS

# 3. Verify services
python .devcontainer/diagnostic.py

# 4. Verify env vars loaded
docker compose exec app bash -c "source /app/global.env && echo \$JOURNALIST_PORT"
# Should output: 8017
```

---

## 📊 DevContainer Components Status

| Component | Status | Port | Notes |
|-----------|--------|------|-------|
| MariaDB | ✅ OK | 3306 | Database initialization automatic |
| ChromaDB | ✅ OK | 3307 | Vector DB stable at v0.4.18 |
| vLLM | ✅ OK | 8001 | Model download takes 5-10 min on first run |
| Django App | ✅ OK | 8100 | Publisher website, migrations automatic |
| Agents | ⚠️ ISSUE | 8000-8020 | Hardcoded ports + missing env vars (see fixes) |

---

## 🔍 What's Working (No Fixes Needed)

✅ Container orchestration (docker compose setup)  
✅ Port mapping and forwarding  
✅ Database initialization and migrations  
✅ Virtual environment creation (via UV)  
✅ Service health checks  
✅ Dependency installation  
✅ GPU support enabled  
✅ Entry point activation  

---

## ⚠️ What's NOT Working (By Design)

❌ Agent microservices not in devcontainer (production deployment, not dev)  
❌ Infrastructure services (Redis, Prometheus, etc.) not in devcontainer  
❌ Crawl4AI not included (separate hosted service)  

**These are intentional - devcontainer is for feature development, not full-stack testing.**

---

## 🎓 Port Allocation Reference

**Critical Devcontainer Ports:**
- 3306: MariaDB
- 3307: ChromaDB
- 8001: vLLM (LLM inference)
- 8100: Django Publisher website

**Agent Service Ports (if running manually in devcontainer):**
- 8000-8020: Reserved for agents (see global.env additions)

---

## 📚 Documentation Files

1. **DEVCONTAINER_DIAGNOSTIC_SUMMARY.md** — Complete 30+ page diagnosis
2. **DEVCONTAINER_FIXES_ACTION_PLAN.md** — Step-by-step fix instructions
3. **DEVCONTAINER_ARCHITECTURE.md** — Visual diagrams & flow charts
4. **.devcontainer/README.md** — Full configuration guide
5. **.devcontainer/SERVICE_STARTUP.md** — Troubleshooting guide

---

## ⏱️ Timeline

| Phase | Time | What Happens |
|-------|------|--------------|
| Build | 2-5 min | Docker downloads CUDA image + installs deps |
| Dependencies | 1-2 min | UV creates venv + installs 100+ packages |
| Startup | 30-60 sec | MariaDB initialization |
| Model Load | 5-10 min | vLLM downloads 14B model (first run only) |
| Post-Create | 20-30 sec | Migrations + health checks |
| **TOTAL** | **~2-3 min** | **Shell prompt ready** *(after first run ~1 min)* |

---

## 🆘 Quick Troubleshooting

**Problem:** Port already in use  
**Solution:** `docker compose down && docker compose up -d`

**Problem:** Connection refused to MariaDB  
**Solution:** Wait 30 seconds for DB to initialize

**Problem:** vLLM won't load model  
**Solution:** Check GPU memory (`nvidia-smi`), verify HF_TOKEN

**Problem:** Migrations fail  
**Solution:** Check MariaDB logs: `docker compose logs mariadb`

**Problem:** Services not starting  
**Solution:** Check docker compose ps: `docker compose ps -a`

---

## 💾 Key Files

| File | Purpose | Status |
|------|---------|--------|
| `.devcontainer/devcontainer.json` | VS Code remote config | ✅ OK |
| `.devcontainer/docker-compose.yaml` | Container orchestration | ✅ OK |
| `.devcontainer/Dockerfile` | App image definition | ✅ OK |
| `.devcontainer/scripts/post-create.sh` | Initialization | ✅ OK |
| `global.env` | Environment config | ⚠️ NEEDS UPDATE (add agent ports) |
| `agents/journalist/main.py` | Agent code | ⚠️ NEEDS FIX (port hardcoded) |

---

## 📋 Pre-Deployment Checklist

- [ ] Journalist port fixed (port 8017, env-driven)
- [ ] global.env updated with agent ports
- [ ] HITL naming improved (optional)
- [ ] Container rebuilds without errors
- [ ] All services show "healthy" in docker compose ps
- [ ] diagnostic.py shows all green checks
- [ ] Environment variables load correctly
- [ ] Shell prompt appears within 3 minutes

---

## 🎯 Next Steps

1. **Read DEVCONTAINER_FIXES_ACTION_PLAN.md** for detailed steps
2. **Apply both critical fixes** (journalist port + global.env)
3. **Run rebuild test** (see Verification section above)
4. **Verify all services healthy**
5. **Mark issues as FIXED** in project tracking

---

**Estimated Total Time to Resolution: 15 minutes**

*For detailed analysis, see accompanying diagnostic documents.*
