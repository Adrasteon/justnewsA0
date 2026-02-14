# JustNews Full System Startup Guide

**Status:** ✅ COMPLETE - System fully operational  
**Date:** 2026-02-10  
**Startup Method:** DevContainer with Docker Compose  
**Data Preservation:** ✅ IDEMPOTENT v2.0 - Workflow data preserved on rebuild

---

## 🔴 CRITICAL: DevContainer Data Preservation (v2.0)

**Your workflow data is now PRESERVED when you rebuild the devcontainer!**

- ✅ Rebuild devcontainer without losing articles, embeddings, or analysis
- ✅ Workflow data automatically preserved across rebuilds
- ✅ Force clean rebuild available if needed: `bash .devcontainer/scripts/pre-build-cleanup.sh --force-clean`

**See**: [`DEVCONTAINER_IDEMPOTENCE_GUARANTEE.md`](DEVCONTAINER_IDEMPOTENCE_GUARANTEE.md) for details.

---

## 🎯 What Was Started

### Infrastructure Services (Docker Compose - Already Running)
- ✅ **MariaDB** (Port 3306) - Persistent database (data preserved on rebuild)
- ✅ **ChromaDB** (Port 3307) - Persistent vector store (embeddings preserved)
- ✅ **vLLM** (Port 8010) - LLM inference engine

### Agent Services (uvicorn - Just Started)
**15/16 agents operational (Scaled & Optimized):**
- ✅ mcp_bus (Port 8000) - Central message bus
- ✅ chief_editor (Port 8001) - Editorial decisions
- ✅ workflow_orchestrator (Port 8023) - Pipeline routing
- ✅ crawler (Port 8022) - Article discovery
- ✅ newsreader (Port 8009) - Feed processing
- ✅ fact_checker (Shim Port 8018 -> backend 8003) - Verification proxy
- ✅ analyst (Port 8004) - Clustering & analysis
- ✅ memory (Port 8007) - Embeddings storage
- ✅ reasoning (Port 8008) - Logic processing
- ✅ critic (Port 8006) - Quality review
- ✅ synthesizer (Port 8005) - **SCALED (2 WORKERS) - NOW OPERATIONAL**
- ✅ crawler_control (Port 8016) - Crawler management
- ✅ gpu_orchestrator (Port 8014) - GPU resource management
- ✅ analytics (Port 8012) - Metrics & analytics
- ✅ archive (Port 8020) - Data archival

**1/16 agents non-critical (skipped):**
- ⚠️ dashboard (Port 8013) - Requires archive_storage/transparency setup

---

## ⚡ Performance Optimization & Scaling

The system is now optimized for the **RTX 3090 (24GB VRAM)**:

- **Multi-Worker Scaling**: Key agents (Fact Checker, Synthesizer) run with multiple workers to fill GPU compute gaps.
- **Lazy Model Loading**: Agents run in "Safe Mode" by default, bypassing heavy local transformers to conserve RAM. 
- **High Concurrency**: The orchestrator is tuned for **30 simultaneous tasks**, maximizing throughput.

To adjust scaling or memory limits, see `system_config.json` and `start_agents_devcontainer.sh`.

---

## 📍 How to Access the System

### API Documentation
Each agent provides Swagger UI at `/docs`:
```bash
http://localhost:8000/docs   # mcp_bus
http://localhost:8001/docs   # chief_editor
http://localhost:8022/docs   # crawler
http://localhost:8023/docs   # workflow_orchestrator
# ... and all other agents on their respective ports
```

### Database Access
```bash
# Connect to MariaDB
mysql -h mariadb -u justnews -pdev_justnews_password justnews

# Quick table check
mysql -h mariadb -u justnews -pdev_justnews_password justnews \
  -e "SELECT COUNT(*) as articles FROM articles; \
      SELECT COUNT(*) as embeddings FROM embeddings_document;"
```

### ChromaDB Vector Store
```bash
# Health check
curl -s http://localhost:3307/api/v2/heartbeat

# List collections
curl -s http://localhost:3307/api/v2/collections
```

### vLLM Inference
```bash
# List available models
curl -s http://localhost:8010/v1/models | python -m json.tool

# Test inference
curl -X POST http://localhost:8010/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "prompt": "Hello, how are you?",
    "max_tokens": 10
  }'
```

### 🛠 Tools & Utilities (DevContainer Native)
The DevContainer environment includes these pre-installed tools for advanced development:

- **Node.js v20**: For JavaScript-based agents and testing (available as `node`).
- **Playwright MCP**: High-performance browser automation (available as `playwright-mcp`).
- **DuckDuckGo Search (ddgs)**: Optimized web search for RAG operations (available in Python venv).
- **UV**: Ultra-fast Python package manager (available as `uv`).

---

## 🔄 How to Restart the Full System

### Option 1: Canonical Startup Script (Recommended)

This is the preferred way to start the entire system, including databases and agents, ensuring correct order and dependency handling.

```bash
# Start all services
./start_all_services.sh

# Stop all services
./stop_all_services.sh
```

### Option 2: Quick Restart (DevContainer only)
```bash
# Stop all agents
pkill -f "uvicorn agents"

# Wait a moment
sleep 2

# Start all agents again
/app/start_agents_devcontainer.sh
```

### Option 2: Complete System Restart
```bash
# From host (Docker Desktop):
cd /app/.devcontainer
docker-compose restart mariadb chromadb vllm

# In devcontainer:
pkill -f "uvicorn agents"
/app/start_agents_devcontainer.sh
```

### Option 3: Full Clean Rebuild (Destructive)
```bash
# From host:
docker-compose down
docker volume rm mariadb_data chromadb_data justnews_data
docker-compose up -d

# In devcontainer:
/app/start_agents_devcontainer.sh
```

---

## 📊 Monitoring the System

### View Agent Logs
```bash
# All agents
tail -f /tmp/justnews_agents_logs/*.log

# Specific agent
tail -f /tmp/justnews_agents_logs/analyst.log

# Error logs
tail -f /tmp/justnews_agents_logs/analyzer.err
```

### Check Agent Health
```bash
# All agents (what we ran earlier)
/tmp/check_agents.sh

# Individual health check
curl -s http://localhost:8000/docs >/dev/null && echo "✓ mcp_bus healthy" || echo "✗ mcp_bus down"
```

### Database Metrics
```bash
# Count articles
mysql -h mariadb -u justnews -pdev_justnews_password justnews \
  -e "SELECT COUNT(*) as total_articles FROM articles;"

# Check embeddings
mysql -h mariadb -u justnews -pdev_justnews_password justnews \
  -e "SELECT COUNT(*) as embeddings_recorded FROM embeddings_document;"

# Pipeline progress
mysql -h mariadb -u justnews -pdev_justnews_password justnews \
  -e "SELECT status, COUNT(*) FROM articles GROUP BY status;"
```

---

## 🔍 Pipeline Execution Checklist

Before running a full pipeline:

- [ ] All 14 core agents are running: `/tmp/check_agents.sh`
- [ ] MariaDB is accessible: `mysql -h mariadb -u justnews -pdev_justnews_password justnews -e "SHOW TABLES;"`
- [ ] ChromaDB is responsive: `curl -s http://localhost:3307/api/v2/heartbeat`
- [ ] vLLM is ready: `curl -s http://localhost:8001/v1/models`

---

## 🚀 Starting a Pipeline Test

### 1. Trigger a Crawl
```bash
curl -X POST http://localhost:8023/api/trigger_crawl \
  -H "Content-Type: application/json" \
  -d '{
    "sources": ["https://news.example.com"]
  }'
```

### 2. Monitor Progress
```bash
# Watch articles being created
watch -n 2 'mysql -h mariadb -u justnews -pdev_justnews_password justnews \
  -e "SELECT COUNT(*) as articles FROM articles; \
      SELECT COUNT(*) as embeddings FROM embeddings_document;"'
```

### 3. Verify Pipeline Stages
```bash
# Check different stages
mysql -h mariadb -u justnews -pdev_justnews_password justnews -e "
  SELECT status, COUNT(*) as count FROM articles GROUP BY status;
  SELECT COUNT(*) as living_stories FROM living_stories;
  SELECT COUNT(*) as synthesized FROM synthesized_articles;
"
```

---

## 📚 Startup Script Reference

The `start_all_services.sh` script is the canonical entry point. It orchestrates the entire startup process:

1. **Environment Setup**: Loads `global.env` and sets up logging.
2. **Database Services**: Starts Redis, checks/starts ChromaDB and MariaDB.
3. **Migrations**: Runs any pending database migrations.
4. **Agents Startup**: Launches all 16 agents using the underlying logic from `start_agents_devcontainer.sh` or explicit startup commands.
5. **Health Verification**: Curls health endpoints for all services.

**Key files involved:**
- Main Script: `/app/start_all_services.sh`
- Agent Logic: `/app/start_agents_devcontainer.sh` (called/referenced for agent-specific logic in some contexts)
- Manifest: `/app/infrastructure/agents_manifest.sh`

---

## ⚠️ Known Issues & Workarounds

### Synthesizer Agent Fails to Start
**Issue:** Looking for transparency audit gateway at wrong endpoint  
**Workaround:** Edit `global.env` to set correct gateway URL, or skip synthesizer for now  
**Status:** Non-critical - pipeline works without it

### Dashboard Agent Fails to Start
**Issue:** Missing `/app/archive_storage/transparency` directory  
**Workaround:** Run `mkdir -p /app/archive_storage/transparency`  
**Status:** Non-critical - UI component

### Ports Already in Use
**Symptom:** "error while attempting to bind on address"  
**Solution:** Kill existing processes: `pkill -f "uvicorn agents"`

### Database Connection Timeout
**Symptom:** "Connection refused" in logs  
**Solution:** Check MariaDB is running: `docker-compose ps`  
**Verify:** `mysql -h mariadb -u justnews -pdev_justnews_password -e "SELECT 1"`

---

## 🔐 Data Persistence

Your data **IS being persisted** across devcontainer reconnects:

- **MariaDB data** → `mariadb_data` Docker volume (persists all tables)
- **ChromaDB data** → `chromadb_data` Docker volume with `IS_PERSISTENT=TRUE`
- **Dependencies** → `justnews_deps` volume (Python virtualenv)
- **Code** → Host bind mount at `/app`

**When you reconnect to the devcontainer, these volumes are reattached automatically.**

---

## 📋 Next Steps

With the system now running:

1. **Test the pipeline** - Follow "Starting a Pipeline Test" above
2. **Review agent logs** - Check `/tmp/justnews_agents_logs/` for any warnings
3. **Verify data flow** - Query database to confirm articles are being processed
4. **Fix non-critical agents** - Set up synthesizer or dashboard if needed
5. **Monitor performance** - Use dashboard/analytics agents (once fixed) for insights

---

## 🆘 Troubleshooting Quick Reference

| Issue | Command | Solution |
|-------|---------|----------|
| Agent won't start | `tail -f /tmp/justnews_agents_logs/{agent}.err` | Check error log |
| Database unreachable | `mysql -h mariadb ... -e "SHOW TABLES"` | Restart MariaDB |
| Port already in use | `ss -tlnp \| grep 8000` | Kill existing process |
| ChromaDB not responding | `curl http://localhost:3307/api/v2/heartbeat` | Restart ChromaDB |
| vLLM too slow | `nvidia-smi` | Check GPU memory usage |
| Agents not registered | `curl http://localhost:8000/agents` | Check mcp_bus logs |

---

**Last Updated:** 2026-02-10  
**System Status:** ✅ **FULLY OPERATIONAL**  
**Ready for:** Pipeline testing, data ingestion, and full workflow execution
