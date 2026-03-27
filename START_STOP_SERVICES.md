# JustNews Service Startup & Shutdown Compatibility Wrappers

This document describes the `start_all_services.sh` and `stop_all_services.sh` compatibility wrappers.

Default behavior is Docker-first:
- `start_all_services.sh` -> Docker compose up
- `stop_all_services.sh` -> Docker compose down

Set `JUSTNEWS_ENABLE_LEGACY_START_STOP=1` to re-enable legacy in-script lifecycle behavior during transition.

## Overview

Docker-first default:
- `./start_all_services.sh` forwards to `scripts/ops/docker_compose.sh up`
- `./stop_all_services.sh` forwards to `scripts/ops/docker_compose.sh down`

Legacy in-script orchestration mode is available only when explicitly enabled:
- `JUSTNEWS_ENABLE_LEGACY_START_STOP=1`

Use legacy mode only for temporary transition scenarios.

## Table of Contents

- [Quick Start](#quick-start)
- [start_all_services.sh](#start_all_servicessh)
- [stop_all_services.sh](#stop_all_servicessh)
- [Use Cases](#use-cases)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Start Everything

```bash
# Start all services (databases + all agents)
./start_all_services.sh

# With verbose logging
VERBOSE=1 ./start_all_services.sh

# Dry run to see what would execute
./start_all_services.sh --dry-run
```

### Stop Everything

```bash
# Graceful shutdown of all services
./stop_all_services.sh

# Force shutdown (immediate kill)
./stop_all_services.sh --force
```

### Start Only Agents (Databases Already Running)

```bash
# Skip database startup
./start_all_services.sh --skip-db

# Start only specific agents
./start_all_services.sh --agents mcp_bus,chief_editor,memory
```

## start_all_services.sh

### Purpose

Starts all JustNews services in the correct dependency order:

1. **Load Environment** - Reads `global.env` configuration
2. **Database Services** - Starts Redis, ChromaDB, MariaDB in sequence
3. **Wait for Readiness** - Waits for database ports to respond
4. **Run Migrations** - Executes schema migrations
5. **Start Agents** - Launches all 17 agents from canonical manifest
6. **Health Verification** - Validates all services are responding

### Usage

```bash
./start_all_services.sh [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--help` | Show help message |
| `--skip-db` | Skip database service startup (assumes already running) |
| `--skip-migrations` | Skip database migrations |
| `--skip-health-check` | Skip health verification |
| `--agents AGENTS` | Comma-separated list of agents to start |
| `--dry-run` | Show commands without executing |

### Examples

```bash
# Start everything
./start_all_services.sh

# Start with verbose output
VERBOSE=1 ./start_all_services.sh

# Start only agents (databases already running)
./start_all_services.sh --skip-db

# Start specific agents only
./start_all_services.sh --agents mcp_bus,crawler,workflow_orchestrator

# Dry run to preview startup sequence
./start_all_services.sh --dry-run

# Skip migrations (if already applied)
./start_all_services.sh --skip-migrations
```

### Crawler Deferred-Ingest Spool (Persistent)

`start_all_services.sh` now sets crawler ingest spool defaults for durability under downstream outages.

Resolution order for `UNIFIED_CRAWLER_INGEST_SPOOL_DIR`:

1. explicit env override
2. `/media/adra/Data/justnews/spool/crawler_ingest`
3. `/media/adra/data/justnews/spool/crawler_ingest`
4. `/var/lib/justnews/spool/crawler_ingest`
5. `/app/runtime/crawler_ingest_spool`

Related env variables:

- `UNIFIED_CRAWLER_INGEST_SPOOL_ENABLED=true`
- `UNIFIED_CRAWLER_INGEST_SPOOL_MAX_ITEMS`
- `UNIFIED_CRAWLER_INGEST_SPOOL_REPLAY_BATCH`
- `UNIFIED_CRAWLER_INGEST_MAX_INFLIGHT`
- `UNIFIED_CRAWLER_INGEST_BACKOFF_SECONDS`

### Output Example

```
2025-02-09T00:00:00Z [INFO] JustNews Service Startup Script
2025-02-09T00:00:00Z [INFO] Repository: /app

=== Loading Environment ===
2025-02-09T00:00:01Z [SUCCESS] Environment loaded

=== Database Services Startup ===
2025-02-09T00:00:02Z [INFO] Starting Redis server...
2025-02-09T00:00:03Z [SUCCESS] Redis is ready on port 6379
2025-02-09T00:00:04Z [INFO] Starting ChromaDB server...
2025-02-09T00:00:05Z [SUCCESS] ChromaDB is ready on port 3307
2025-02-09T00:00:06Z [INFO] Starting MariaDB daemon...
2025-02-09T00:00:10Z [SUCCESS] MariaDB is ready on port 3306

=== Running Database Migrations ===
2025-02-09T00:00:11Z [INFO] Running Django migrations...
2025-02-09T00:00:20Z [SUCCESS] Django migrations completed

=== Agents Startup (17 agents) ===
2025-02-09T00:00:21Z [INFO] Starting mcp_bus on port 8000...
2025-02-09T00:00:23Z [SUCCESS] mcp_bus is ready on port 8000
...
```

### Log Files

Service logs are written to `/tmp/justnews_services_logs/`:

```
/tmp/justnews_services_logs/
├── chromadb.log
├── redis.log
├── mcp_bus.log
├── chief_editor.log
├── crawler.log
└── ...
```

### Environment Variables

```bash
# Control script behavior
VERBOSE=1              # Show verbose debug output
DRY_RUN=1             # Show commands without executing
SKIP_DB=1             # Skip database startup
SKIP_MIGRATIONS=1     # Skip migrations
SKIP_HEALTH_CHECK=1   # Skip health verification

# Timing
SERVICE_TIMEOUT=120    # Timeout for service readiness (seconds)
AGENT_START_DELAY=2    # Delay between agent starts (seconds)

# Host RAM guardrail (default cap: 85% used)
JUSTNEWS_RAM_CAP_ENFORCE=1                  # Enforce RAM usage gate before each service start
JUSTNEWS_RAM_CAP_PERCENT=85                 # Block startup when host RAM usage is at/above this percent
JUSTNEWS_RAM_CAP_WAIT_SECONDS=120           # Max seconds to wait for usage to drop below cap
JUSTNEWS_RAM_CAP_CHECK_INTERVAL_SECONDS=5   # Poll interval while waiting for RAM headroom

# Runtime memory governor (lifecycle moderation; environment-agnostic)
JUSTNEWS_MEMORY_GOVERNOR_ENABLED=1          # Enable runtime governor daemon
JUSTNEWS_MEMORY_SOFT_PERCENT=85             # Pause one non-critical process at/above this usage
JUSTNEWS_MEMORY_HARD_PERCENT=88             # Pause/terminate non-critical process at/above this usage
JUSTNEWS_MEMORY_EMERGENCY_PERCENT=92        # Shed highest-RSS non-critical process at/above this usage
JUSTNEWS_MEMORY_RESUME_PERCENT=80           # Resume paused processes below this usage
JUSTNEWS_MEMORY_CHECK_INTERVAL_SECONDS=5    # Poll interval for runtime governor
JUSTNEWS_MEMORY_ACTION_COOLDOWN_SECONDS=20  # Minimum seconds between governor actions
JUSTNEWS_MEMORY_TERMINATE_GRACE_SECONDS=12  # Grace period before SIGKILL

# Workflow autonomic controller (orchestrator)
AUTONOMIC_MODE=shadow                        # disabled|shadow|active
AUTONOMIC_DECISIONS_ENABLED=1                # Enable decision cycle
AUTONOMIC_LEARNING_ENABLED=1                 # Keep learning telemetry in shadow mode

# Database configuration (usually from global.env)
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_USER=justnews
MARIADB_PASSWORD=dev_justnews_password
MARIADB_DB=justnews

CHROMADB_HOST=localhost
CHROMADB_PORT=3307

REDIS_HOST=localhost
REDIS_PORT=6379

# Crawler ingest resiliency
UNIFIED_CRAWLER_INGEST_SPOOL_ENABLED=true
UNIFIED_CRAWLER_INGEST_SPOOL_DIR=/var/lib/justnews/spool/crawler_ingest
UNIFIED_CRAWLER_INGEST_SPOOL_MAX_ITEMS=2500
UNIFIED_CRAWLER_INGEST_SPOOL_REPLAY_BATCH=25
UNIFIED_CRAWLER_INGEST_MAX_INFLIGHT=6
UNIFIED_CRAWLER_INGEST_BACKOFF_SECONDS=8

# Memory pressure mitigation
MEMORY_ESSENTIAL_MODE=true
```

### Runtime Memory Governor Behavior

- The startup script launches `scripts/ops/justnews_memory_governor.py` after services pass startup/verification.
- Governor logic is tiered to avoid brittle behavior:
	- soft pressure: pause one non-critical process (`SIGSTOP`)
	- hard pressure: pause additional process, then terminate one non-critical process if pressure persists
	- emergency pressure: terminate highest-RSS non-critical process
	- recovery window: resume paused processes (`SIGCONT`) once memory drops below resume threshold
- Critical core services (`mcp_bus`, `memory`) are protected from governor termination actions.
- Governor state/log files:
	- `/tmp/justnews_services_logs/memory_governor/justnews_memory_governor.log`
	- `/tmp/justnews_services_logs/memory_governor/justnews_memory_governor_state.json`

### Workflow Autonomic Shadow Telemetry

- The workflow orchestrator exposes shadow/autonomic state at:
	- `GET http://localhost:8023/autonomic/status`
- In shadow mode (`AUTONOMIC_MODE=shadow`), decisions are recorded without runtime patch application.
- Latest shadow-decision visibility is available in logs via:
	- `Autonomic shadow decision recorded: status=<...> reason=<...> patch=<...>`
	- log file: `/tmp/justnews_services_logs/workflow_orchestrator.startup.log`

## stop_all_services.sh

### Purpose

Gracefully shuts down all JustNews services in reverse order:

1. **Stop All Agents** - Graceful shutdown via /shutdown endpoint or forced kill
2. **Stop Database Services** - Stop MariaDB, ChromaDB, Redis
3. **Cleanup** - Verify all processes terminated

### Usage

```bash
./stop_all_services.sh [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--help` | Show help message |
| `--force` | Force kill services without graceful shutdown |
| `--skip-db` | Don't stop database services |

### Examples

```bash
# Graceful shutdown of all services
./stop_all_services.sh

# Force shutdown (immediate kills)
./stop_all_services.sh --force

# Stop only agents (keep databases running)
./stop_all_services.sh --skip-db

# Verbose shutdown
VERBOSE=1 ./stop_all_services.sh
```

### Graceful Shutdown Process

For each service:

1. **Attempt HTTP Request** - Send POST to `/shutdown` endpoint (timeout 3s)
2. **Wait for Port Close** - Wait up to 10 seconds for port to close
3. **Force Kill (if needed)** - If still not stopped, kill processes (SIGTERM then SIGKILL)

### Output Example

```
2025-02-09T00:05:00Z [INFO] JustNews Service Shutdown Script

=== Stopping All Agents ===
2025-02-09T00:05:01Z [INFO] Stopping mcp_bus on port 8000...
2025-02-09T00:05:01Z [SUCCESS] mcp_bus stopped gracefully
2025-02-09T00:05:02Z [INFO] Stopping chief_editor on port 8001...
2025-02-09T00:05:03Z [SUCCESS] chief_editor stopped gracefully
...

=== Stopping Database Services ===
2025-02-09T00:05:30Z [INFO] Stopping MariaDB on port 3306...
2025-02-09T00:05:31Z [SUCCESS] MariaDB stopped
...

=== Shutdown Complete ===
2025-02-09T00:05:35Z [SUCCESS] All services have been stopped
```

## Use Cases

### Development Setup

Start fresh development environment:

```bash
# Make sure you have global.env configured
cp global.env.sample global.env
# Edit global.env with your configuration

# Start everything
./start_all_services.sh

# Services will be available at:
# - Dashboard: http://localhost:8013
# - MCP Bus: http://localhost:8000
# - Memory Agent: http://localhost:8007
```

### Docker-Based Deployment

Start databases via Docker, agents locally:

```bash
# Terminal 1: Start databases
cd infrastructure/docker
docker compose up -d mariadb chromadb redis

# Terminal 2: Start agents only
./start_all_services.sh --skip-db
```

### Production Deployment with Systemd

```bash
# Start services for production
# Set environment variables
export SERVICE_TIMEOUT=60
export SKIP_HEALTH_CHECK=1

# Start in background (daemonized)
# Can be configured with systemd service
./start_all_services.sh &

# Check status periodically
sleep 30
curl -s http://localhost:8000/health | jq .
```

### Debug Specific Agent

Start only problematic agent for debugging:

```bash
# Stop all services first
./stop_all_services.sh

# Start only needed services
./start_all_services.sh --agents mcp_bus,memory,chief_editor

# Run failing agent manually for debugging
./start_all_services.sh --agents failing_agent
```

### Restart Single Agent

Restart one agent without stopping everything:

```bash
# Find the agent port from infrastructure/agents_manifest.sh
# Kill the port
fuser -k 8001/tcp

# Wait a moment
sleep 2

# Restart via start_all_services
./start_all_services.sh --agents chief_editor
```

### Continuous Integration

Safe non-blocking startup:

```bash
# Start with timeout, don't fail on health checks
./start_all_services.sh --skip-health-check &
start_pid=$!

# Wait for startup to complete (max 2 min)
sleep 120

# Run tests
pytest tests/

# Cleanup
kill ${start_pid}
./stop_all_services.sh --force
```

## Environment Variables

### Script Control

```bash
# Verbosity and modes
VERBOSE=1                    # Show debug output
DRY_RUN=1                   # Show what would run without executing
FORCE=1                     # (stop script) force kill without graceful

# Skip flags
SKIP_DB=1                   # Skip database startup
SKIP_MIGRATIONS=1           # Skip migrations
SKIP_HEALTH_CHECK=1         # Skip health verification (start script only)

# Timing
SERVICE_TIMEOUT=120         # Timeout for service readiness (seconds)
AGENT_START_DELAY=2         # Delay between agent starts (seconds)
GRACEFUL_TIMEOUT=10         # (stop script) timeout for graceful shutdown
KILL_TIMEOUT=3              # (stop script) timeout for kill signal
```

### Database Configuration

These come from `global.env` and can be overridden:

```bash
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_USER=justnews
MARIADB_PASSWORD=dev_justnews_password
MARIADB_DB=justnews

CHROMADB_HOST=localhost
CHROMADB_PORT=3307

REDIS_HOST=localhost
REDIS_PORT=6379
```

### Agent Configuration

Agent ports and modules are from `infrastructure/agents_manifest.sh`:

```bash
# Used automatically from manifest
# Example entries:
# "mcp_bus|agents.mcp_bus.main:app|8000"
# "chief_editor|agents.chief_editor.main:app|8001"
# etc.
```

## Troubleshooting

### All Services Start But One Agent Fails

```bash
# Check if the agent's port is already in use
netstat -tlnp | grep :8001  # Replace 8001 with the failing agent's port

# Kill any process using that port
fuser -k 8001/tcp

# Check the agent's log file
tail -f /tmp/justnews_services_logs/chief_editor.log

# Try starting just that agent
./start_all_services.sh --agents chief_editor
```

### MariaDB Port Already in Use

```bash
# Check what's using MariaDB port
netstat -tlnp | grep 3306

# Try to kill it gracefully
mysql -u root -p -e "SHUTDOWN;"

# Or force kill
fuser -k 3306/tcp

# Restart
./stop_all_services.sh
./start_all_services.sh
```

### ChromaDB Not Responding

```bash
# Check if ChromaDB started
ps aux | grep chroma

# Check the log
tail -f /tmp/justnews_services_logs/chromadb.log

# Verify Python has chromadb package
python3 -c "import chroma; print(chroma.__version__)"

# If not installed:
pip install chromadb
```

### Services Not Stopping Gracefully

```bash
# Use force stop
./stop_all_services.sh --force

# Or manually kill
killall python  # Be careful!

# Force kill specific port
fuser -k 8000/tcp 8001/tcp 8002/tcp
```

### Health Check Failures

```bash
# Check a specific service
curl -v http://localhost:8000/health
curl -v http://localhost:8007/health

# Skip health checks if they're not critical
SKIP_HEALTH_CHECK=1 ./start_all_services.sh
```

### Migrations Failed

```bash
# Check migration logs
tail /tmp/justnews_services_logs/*

# Check Django migration status
python manage.py showmigrations

# Run migrations manually
python manage.py migrate

# Try again with script
./start_all_services.sh --skip-db
```

### Port Conflicts

```bash
# Find what's using a port
lsof -i :8000
netstat -tlnp | grep 8000

# List all JustNews services
ps aux | grep "agents\."

# Kill specific agent
kill ${PID}

# Or restart everything
./stop_all_services.sh --force
./start_all_services.sh
```

## Performance Tuning

### Faster Startup (Skip Non-Critical Steps)

```bash
# Skip health checks if time is critical
SKIP_HEALTH_CHECK=1 ./start_all_services.sh

# Skip migrations if already applied
./start_all_services.sh --skip-migrations

# Reduce agent startup delay
AGENT_START_DELAY=0.5 ./start_all_services.sh
```

### Slower Startup (More Reliable)

```bash
# Increase timeouts for slow systems
SERVICE_TIMEOUT=300 AGENT_START_DELAY=5 ./start_all_services.sh

# Use verbose mode to monitor progress
VERBOSE=1 ./start_all_services.sh
```

## Integration with systemd

Example systemd service file for production:

```ini
[Unit]
Description=JustNews All Services
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
User=justnews
WorkingDirectory=/app
Environment="SKIP_HEALTH_CHECK=1"
ExecStart=/app/start_all_services.sh
ExecStop=/app/stop_all_services.sh --force
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

Install and enable:

```bash
sudo cp justnews.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable justnews
sudo systemctl start justnews

# Monitor
sudo systemctl status justnews
sudo journalctl -u justnews -f
```

## Canonical Agent List

These are the 16 agents started by the scripts (from `infrastructure/agents_manifest.sh`):

| Agent | Port | Purpose |
|-------|------|---------|
| mcp_bus | 8000 | Message broker - **MUST start first** |
| chief_editor | 8001 | Main editorial orchestration |
| fact_checker | 8003 | Fact validation |
| analyst | 8004 | Data analysis |
| synthesizer | 8005 | Content synthesis |
| critic | 8006 | Quality review |
| memory | 8007 | Data persistence & retrieval |
| reasoning | 8008 | Logical reasoning |
| newsreader | 8009 | News feed processing |
| analytics | 8012 | Analytics dashboard |
| dashboard | 8013 | Web dashboard |
| gpu_orchestrator | 8014 | GPU resource management |
| crawler_control | 8016 | Crawler UI control |
| archive | 8020 | Article archival |
| crawler | 8022 | Web crawler engine |
| workflow_orchestrator | 8023 | Workflow coordination |

## Best Practices

1. **Always Load Environment First** - Scripts automatically load `global.env`
2. **Start Databases First** - Database services start before agents
3. **MCP Bus First** - Agents depend on message bus being ready
4. **Check Logs** - Logs are in `/tmp/justnews_services_logs/`
5. **Graceful Shutdown** - Use default shutdown, not `--force` unless needed
6. **Health Verification** - Run health checks to verify startup
7. **Dry Run for Learning** - Use `--dry-run` to see startup sequence
8. **Environment Variables** - Set via shell or `.env` before running

## Related Scripts

- [infrastructure/agents_manifest.sh](../../infrastructure/agents_manifest.sh) - Canonical agent definitions
- [global.env](../../global.env) - Environment configuration
- [global.env.sample](../../global.env.sample) - Environment template
- [start_dev_system.py](../../start_dev_system.py) - Python-based dev startup
- [scripts/stop_services.sh](../../scripts/stop_services.sh) - Legacy stop script

## See Also

- [docs/operations/STARTUP_CHECKLIST.md](../operations/STARTUP_CHECKLIST.md) - Quick startup checklist
- [docs/architecture_overview.md](../architecture_overview.md) - System architecture
- [README.md](../../README.md) - Project overview
