# JustNews Service Startup/Shutdown - Quick Reference

## TL;DR - Getting Started Fast

```bash
# Start EVERYTHING (databases + 16 agents)
./start_all_services.sh

# Watch the startup (verbose)
VERBOSE=1 ./start_all_services.sh

# See what would happen (dry run)
./start_all_services.sh --dry-run

# Stop everything gracefully
./stop_all_services.sh

# Force stop everything (if stuck)
./stop_all_services.sh --force
```

## Canonical Scripts at a Glance

| Script | Purpose | Key Features |
|--------|---------|--------------|
| **start_all_services.sh** | Start databases + all 16 agents | Ordered startup, health checks, migrations |
| **stop_all_services.sh** | Graceful shutdown of all services | Reverse order, graceful first, force fallback |

## Common Startup Scenarios

### Scenario 1: Fresh Start (Empty System)
```bash
# Everything from scratch
./start_all_services.sh
```
**Output**: All services ready in 1-2 minutes

### Scenario 2: Agents Only (Databases Already Running)
```bash
# Docker Compose databases already running
./start_all_services.sh --skip-db

# Or just specific agents
./start_all_services.sh --agents mcp_bus,crawler,workflow_orchestrator
```

### Scenario 3: Skip Non-Critical Steps
```bash
# Fast startup (skip migrations,  health checks)
./start_all_services.sh --skip-migrations --skip-health-check
```

### Scenario 4: Development with Debugging
```bash
# Verbose output for troubleshooting
VERBOSE=1 ./start_all_services.sh

# Check logs
tail -f /tmp/justnews_services_logs/*.log
```

## Service Architecture (Startup Order)

```
1. Load Environment (global.env)
   ↓
2. Database Services (parallel startup)
   ├─ Redis (port 6379)
   ├─ ChromaDB (port 3307)
   └─ MariaDB (port 3306)
   ↓
3. Migrations
   ├─ Django migrations
   └─ App migrations
   ↓
4. Agents (sequential, MCP Bus first)
   mcp_bus (8000) → all others depend on this
   ├─ chief_editor (8001)
   ├─ fact_checker (8003)
   ├─ analyst (8004)
   ├─ synthesizer (8005)
   ├─ critic (8006)
   ├─ memory (8007)
   ├─ reasoning (8008)
   ├─ newsreader (8009)
   ├─ analytics (8012)
   ├─ dashboard (8013)
   ├─ gpu_orchestrator (8014)
   ├─ crawler_control (8016)
   ├─ archive (8020)
   ├─ crawler (8022)
   └─ workflow_orchestrator (8023)
```

## All Available Options

### start_all_services.sh

```bash
./start_all_services.sh [OPTIONS]

--help                    Show help
--skip-db                Skip database startup
--skip-migrations         Skip database migrations
--skip-health-check      Skip health verification
--agents AGENT1,AGENT2   Start only these agents
--dry-run                Show what would run

# Environment variables
VERBOSE=1              Debug output
DRY_RUN=1             Dry run mode
SKIP_DB=1             Skip databases
SKIP_MIGRATIONS=1     Skip migrations
SKIP_HEALTH_CHECK=1   Skip health checks
SERVICE_TIMEOUT=120   Service ready timeout (sec)
AGENT_START_DELAY=2   Delay between agents (sec)
```

### stop_all_services.sh

```bash
./stop_all_services.sh [OPTIONS]

--help                Show help
--force               Force kill (no graceful)
--skip-db            Keep databases running

# Environment variables
VERBOSE=1            Debug output
FORCE=1              Force kill
SKIP_DB=1            Skip stopping databases
GRACEFUL_TIMEOUT=10  Grace period (sec)
KILL_TIMEOUT=3       Kill signal timeout (sec)
```

## Key Service Endpoints

| Service | Port | URL |
|---------|------|-----|
| MCP Bus | 8000 | http://localhost:8000 |
| Chief Editor | 8001 | http://localhost:8001 |
| Fact Checker | 8003 | http://localhost:8003 |
| Analyst | 8004 | http://localhost:8004 |
| Synthesizer | 8005 | http://localhost:8005 |
| Critic | 8006 | http://localhost:8006 |
| Memory | 8007 | http://localhost:8007 |
| Reasoning | 8008 | http://localhost:8008 |
| Newsreader | 8009 | http://localhost:8009 |
| Analytics | 8012 | http://localhost:8012 |
| Dashboard | 8013 | http://localhost:8013 |
| GPU Orchestrator | 8014 | http://localhost:8014 |
| Crawler Control | 8016 | http://localhost:8016 |
| Archive | 8020 | http://localhost:8020 |
| Crawler | 8022 | http://localhost:8022 |
| Workflow Orchestrator | 8023 | http://localhost:8023 |
| **MariaDB** | 3306 | localhost:3306 |
| **ChromaDB** | 3307 | localhost:3307 |
| **Redis** | 6379 | localhost:6379 |

## Log Files

All service logs written to: `/tmp/justnews_services_logs/`

```bash
# Watch all logs
tail -f /tmp/justnews_services_logs/*.log

# Watch specific service
tail -f /tmp/justnews_services_logs/memory.log

# Check for errors
grep ERROR /tmp/justnews_services_logs/*.log

# Tail last 100 lines
tail -100 /tmp/justnews_services_logs/chief_editor.log
```

## Health Checking

```bash
# Check MCP Bus (core service)
curl http://localhost:8000/health

# Check Memory Agent
curl http://localhost:8007/health

# Check Crawler
curl http://localhost:8022/health

# Check all agents (basic port check)
for port in 8000 8001 8003 8004 8005 8006 8007 8008 8009 8012 8013 8014 8016 8020 8022 8023; do
  nc -z localhost $port 2>/dev/null && echo "Port $port: OK" || echo "Port $port: DOWN"
done
```

## Troubleshooting Quick Fixes

### Port Already in Use
```bash
# Find what's using port 8000
lsof -i :8000

# Kill it gracefully
fuser -k 8000/tcp

# Or find and kill process
ps aux | grep :8000
kill ${PID}
```

### MariaDB Connection Refused
```bash
# Check if MariaDB is running
ps aux | grep mysql

# Try restart
./stop_all_services.sh
./start_all_services.sh
```

### Agent Not Starting
```bash
# View its log
tail -50 /tmp/justnews_services_logs/AGENT_NAME.log

# Start just that agent
./start_all_services.sh --agents AGENT_NAME

# Check if port in use
nc -z localhost 8001 && echo "Port in use" || echo "Port free"
```

### Everything Stuck
```bash
# Force stop everything
./stop_all_services.sh --force

# Kill remaining processes
killall python 2>/dev/null || true

# Clean ports
fuser -k 3306/tcp 3307/tcp 6379/tcp 8000-8023/tcp 2>/dev/null || true

# Fresh start
./start_all_services.sh
```

## Environment Configuration

### Required (from global.env)
- `MARIADB_HOST`, `MARIADB_PORT`, `MARIADB_USER`, `MARIADB_PASSWORD`
- `CHROMADB_HOST`, `CHROMADB_PORT`

### Optional
- `REDIS_HOST`, `REDIS_PORT` (defaults: localhost:6379)
- `SERVICE_TIMEOUT` (default: 120s)
- `AGENT_START_DELAY` (default: 2s)

## Performance Notes

### Startup Times (Typical)
- Database services: ~30-60 seconds
- Migrations: ~10-30 seconds  
- All 16 agents: ~1-2 minutes
- **Total**: 2-3 minutes full startup

### Fastest Startup
```bash
./start_all_services.sh --skip-db --skip-migrations
# ~30-60 seconds (agents only)
```

### Slowest Startup (Most Reliable)
```bash
SERVICE_TIMEOUT=300 AGENT_START_DELAY=5 ./start_all_services.sh
# ~5+ minutes (longer timeouts, more delays)
```

## Integration Examples

### Docker Compose + Script
```bash
# Terminal 1: Start database services
cd infrastructure/docker
docker-compose up mariadb chromadb redis

# Terminal 2: Start agents only
./start_all_services.sh --skip-db
```

### Systemd Service
```bash
# Create service file (see full docs)
sudo systemctl start justnews
sudo systemctl status justnews
sudo journalctl -u justnews -f
```

### CI/CD Pipeline
```bash
# Start silently for testing
./start_all_services.sh >/dev/null 2>&1 &
sleep 120

# Run tests
pytest tests/

# Cleanup
./stop_all_services.sh --force
```

## Documentation

- **Full Documentation**: [START_STOP_SERVICES.md](START_STOP_SERVICES.md)
- **Agent Manifest**: [infrastructure/agents_manifest.sh](infrastructure/agents_manifest.sh)
- **Environment Template**: [global.env.sample](global.env.sample)
- **Architecture**: [docs/architecture_overview.md](docs/architecture_overview.md)

## Quick Commands Reference

```bash
# Start everything
./start_all_services.sh

# Dry run to see what would happen
./start_all_services.sh --dry-run

# Start with debug output
VERBOSE=1 ./start_all_services.sh

# Skip databases (already running)
./start_all_services.sh --skip-db

# Start only critical services
./start_all_services.sh --agents mcp_bus,memory,crawler

# Stop gracefully
./stop_all_services.sh

# Force stop
./stop_all_services.sh --force

# Watch logs
tail -f /tmp/justnews_services_logs/*.log

# Check health
curl http://localhost:8000/health

# List running services
ps aux | grep "agents\."

# Find what's using a port
lsof -i :8000

# Kill stuck service
fuser -k 8001/tcp
```

---

**For detailed documentation, see**: [START_STOP_SERVICES.md](START_STOP_SERVICES.md)
**For agent definitions, see**: [infrastructure/agents_manifest.sh](infrastructure/agents_manifest.sh)
