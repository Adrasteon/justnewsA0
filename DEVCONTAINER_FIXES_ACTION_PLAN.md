# DevContainer Issues - ACTION PLAN & FIXES

**Date:** February 9, 2026  
**Total Estimated Time:** 10 minutes to fix all critical issues

---

## Priority 1: 🔴 FIX Journalist Agent Port Conflict (CRITICAL)

### Issue
Journalist agent hardcoded to port 8016, conflicts with Crawler Control agent which should use 8016.

### Location
**File:** `agents/journalist/main.py`  
**Line:** 97

### Current Code
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8016)  # ❌ HARDCODED
```

### Fixed Code
```python
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("JOURNALIST_PORT", 8017))
    uvicorn.run(app, host="0.0.0.0", port=port)  # ✅ ENVIRONMENT-DRIVEN
```

### Changes
- [ ] Add `import os` at the top if not present
- [ ] Replace hardcoded `port=8016` with environment variable
- [ ] Use default value `8017` (prevents startup failure if env var missing)
- [ ] Change `host="127.0.0.1"` to `host="0.0.0.0"` (allows container network access)

### Verification
After fix, verify with:
```bash
# Inside container, try starting both agents on correct ports:
CRAWLER_CONTROL_AGENT_PORT=8016 python -m agents.crawler_control.main &
JOURNALIST_PORT=8017 python -m agents.journalist.main &

# Both should start without port conflict
```

**Time: 5 minutes**

---

## Priority 2: 🟡 ADD Agent Port Environment Variables (MEDIUM)

### Issue
`global.env` is missing 18+ agent port environment variables, preventing consistent agent configuration.

### Location
**File:** `global.env`

### Current State
The file has sections for:
- Database configuration ✅
- ChromaDB configuration ✅
- Publisher website ✅
- vLLM configuration ✅
- Django settings ✅
- Observability ✅

But **missing** agent ports entirely.

### What to Add

Find the end of the "System Tuning" section (should be around line 40-50), and add:

```bash
# ==============================================================================
# Agent Service Ports (Used when running agents within devcontainer)
# ==============================================================================
# These environment variables allow agents to be started independently
# with consistent port configuration. They are optional in the devcontainer
# but required if manually testing agents.

# Core Agents
MCP_BUS_PORT=8000
CHIEF_EDITOR_AGENT_PORT=8001
SCOUT_AGENT_PORT=8002
FACT_CHECKER_AGENT_PORT=8003
ANALYST_AGENT_PORT=8004
SYNTHESIZER_AGENT_PORT=8005
CRITIC_AGENT_PORT=8006
MEMORY_AGENT_PORT=8007
REASONING_AGENT_PORT=8008
NEWSREADER_PORT=8009
ANALYTICS_AGENT_PORT=8011
ARCHIVE_AGENT_PORT=8012

# Advanced Agents
DASHBOARD_PORT=8013
GPU_ORCHESTRATOR_PORT=8014
CRAWLER_AGENT_PORT=8015
CRAWLER_CONTROL_AGENT_PORT=8016
JOURNALIST_PORT=8017
AUTH_SERVICE_PORT=8018
HITL_SERVICE_PORT=8019
WORKFLOW_ORCHESTRATOR_PORT=8020

# Service URLs (for client connections)
MCP_BUS_URL=http://localhost:8000
VLLM_BASE_URL=http://vllm:8001/v1

# Optional: Infrastructure Services (if running locally)
REDIS_URL=redis://localhost:6379
REDIS_PORT=6379
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
```

### Verification
After adding, verify the file loads correctly:
```bash
# Inside container:
source global.env
echo $JOURNALIST_PORT
# Should output: 8017
```

**Time: 5 minutes**

---

## Priority 3: 🟡 IMPROVE HITL Service Port Naming (LOW - Optional)

### Issue
HITL service uses dual naming conventions with different defaults, causing confusion.

### Location
**File:** `agents/hitl_service/main.py`  
**Line:** 30  
**Also in:** `app.py` line 31

### Current Code Pattern
```python
# Somewhere in HITL service startup code:
port = int(os.environ.get("HITL_SERVICE_PORT", default_to_hitl_port))
# This works but isn't explicit about the fallback logic
```

### Recommended Pattern
```python
# More explicit and documented fallback:
port = int(os.environ.get(
    "HITL_SERVICE_PORT", 
    os.environ.get("HITL_PORT", 8019)  # Explicit fallback chain
))
```

Or add a comment explaining the behavior:
```python
# Supports both new (HITL_SERVICE_PORT) and legacy (HITL_PORT) environment variables
# for backward compatibility. New code should use HITL_SERVICE_PORT.
port = int(os.environ.get("HITL_SERVICE_PORT", 8019))
```

### Note
**This is low priority.** The current implementation works fine. Only address if you're refactoring the codebase for consistency.

**Time: 5 minutes (if doing it)**

---

## Testing Checklist

### After Applying Fixes

- [ ] **Container Builds Successfully**
  ```bash
  docker-compose down
  docker-compose build
  docker-compose up -d
  ```

- [ ] **Initialization Completes**
  ```bash
  # Check logs
  docker-compose logs app | tail -30
  # Should show: [✓ SUCCESS] Dev Container Initialization Complete!
  ```

- [ ] **Services Accessible**
  ```bash
  # From host:
  curl -s http://localhost:3306 >/dev/null && echo "✓ MariaDB"
  curl -s http://localhost:3307/api/v1/heartbeat | grep -q 'version' && echo "✓ ChromaDB"
  curl -s http://localhost:8001/v1/models | grep -q 'models' && echo "✓ vLLM"
  ```

- [ ] **Journalist Port Fixed**
  ```bash
  # Inside container:
  JOURNALIST_PORT=8017 python -c "
  from agents.journalist.main import app
  import os
  print(f'Port: {os.environ.get(\"JOURNALIST_PORT\", \"Not set\")}')
  # Should show: Port: 8017
  "
  ```

- [ ] **Agent Ports Loaded**
  ```bash
  # Inside container:
  source /app/global.env
  echo "MCP_BUS_PORT=$MCP_BUS_PORT"
  echo "JOURNALIST_PORT=$JOURNALIST_PORT"
  # Should show both ports
  ```

---

## Implementation Steps

### Step 1: Fix Journalist Port (5 min)
1. Open `agents/journalist/main.py`
2. Find line 97 (the `if __name__ == "__main__":` block)
3. Replace hardcoded port with environment variable (see code examples above)
4. Add `import os` if needed
5. Change `host="127.0.0.1"` to `host="0.0.0.0"`

### Step 2: Add Agent Ports to global.env (5 min)
1. Open `global.env`
2. Find the end of "System Tuning" section
3. Add the complete "Agent Service Ports" block (see section above)
4. Save file

### Step 3: Rebuild & Test (5 min)
```bash
# From host terminal:
cd /app

# Rebuild devcontainer
docker-compose down
docker-compose build
docker-compose up -d

# Verify initialization
docker-compose logs app -f

# Test services
python .devcontainer/diagnostic.py

# Inside container, verify ports loaded
source /app/global.env
echo $JOURNALIST_PORT    # Should be 8017
echo $CRAWLER_CONTROL_AGENT_PORT  # Should be 8016
```

---

## Rollback Plan

If something breaks, here's how to revert:

### Revert Journalist Port Fix
```bash
# If journalist.py change causes issues, revert to:
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8016)
```

### Revert global.env Changes
```bash
# If env vars cause issues, remove the Agent Section:
# Simply delete everything between the "Agent Service Ports" markers
# Leave the rest of the file unchanged
```

### Full Rebuild
```bash
# Nuclear option - start fresh:
docker-compose down
docker volume rm mariadb_data chromadb_data
git checkout agents/journalist/main.py global.env
docker-compose up -d
```

---

## Success Indicators

After fixes are applied, you should see:

✅ Container initializes without errors  
✅ Shell prompt appears within 2-3 minutes  
✅ All services show "healthy" in `docker-compose ps`  
✅ `python .devcontainer/diagnostic.py` shows all green  
✅ Environment variables load: `source global.env && echo $JOURNALIST_PORT`  
✅ Journalist can start on port 8017: `JOURNALIST_PORT=8017 python -m agents.journalist.main`  

---

## Documentation Updates (Optional)

After fixes, consider updating:

1. **`.devcontainer/README.md`**: Add section about agent ports
   - Link to this action plan
   - Examples of running agents inside devcontainer

2. **New file `.devcontainer/AGENT_TESTING_GUIDE.md`**: Document how to:
   - Start individual agents for testing
   - Avoid port conflicts
   - Test agent-to-agent communication

3. **Update `DEVCONTAINER_DIAGNOSTIC_SUMMARY.md`**: Mark issues as FIXED

---

## Summary

| Fix | File | Line(s) | Time | Complexity |
|-----|------|---------|------|-----------|
| Journalist port | `agents/journalist/main.py` | 97 | 5 min | ⭐ Easy |
| Agent ports env vars | `global.env` | End of file | 5 min | ⭐ Easy |
| HITL naming (optional) | `agents/hitl_service/main.py` | 30 | 5 min | ⭐ Easy |
| Test & rebuild | Various | — | 5 min | ⭐ Easy |
| **Total** | — | — | **20 min** | **All Easy** |

**All three fixes are straightforward and low-risk.**

---

## Questions?

If any of these fixes are unclear:

1. Refer back to [DEVCONTAINER_DIAGNOSTIC_SUMMARY.md](DEVCONTAINER_DIAGNOSTIC_SUMMARY.md) for context
2. Check [DEVCONTAINER_ARCHITECTURE.md](DEVCONTAINER_ARCHITECTURE.md) for architecture overview
3. Review `.devcontainer/README.md` for detailed configuration
4. Check `.devcontainer/SERVICE_STARTUP.md` for troubleshooting

All documentation is comprehensive and cross-referenced.

---

*Action Plan created: February 9, 2026*
