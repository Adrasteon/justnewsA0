#!/usr/bin/env bash
# start_services_daemon.sh
# Starts the justnews set of FastAPI/uvicorn agent services using the
# `justnews-py312-phase1` conda environment. Performs simple health checks and
# writes per-agent logs to ./logs/

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Conda environment name used by the project
CANONICAL_ENV="${CANONICAL_ENV:-justnews-py312-phase1}"

# Default timeout for healthchecks (seconds)
HEALTH_TIMEOUT=60

# Agent definitions: name|python_module:app|port
# Keep this list in sync with agents/*/main.py and the dashboard mapping
AGENTS=(
  "mcp_bus|agents.mcp_bus.main:app|8000"
  "chief_editor|agents.chief_editor.main:app|8001"
  # "scout|agents.scout.main:app|8002"
  "fact_checker|agents.fact_checker.main:app|8003"
  "analyst|agents.analyst.main:app|8004"
  "synthesizer|agents.synthesizer.main:app|8005"
  "critic|agents.critic.main:app|8006"
  "memory|agents.memory.main:app|8007"
  "reasoning|agents.reasoning.main:app|8008"
  # "newsreader|agents.newsreader.main:app|8009"
  # db_worker removed
  "dashboard|agents.dashboard.main:app|8013"
  "analytics|agents.analytics.dashboard:analytics_app|8012"
  # Balancer removed - responsibilities moved to critic/analytics/gpu_orchestrator
  # Newly added GPU orchestrator service (was missing previously)
  "gpu_orchestrator|agents.gpu_orchestrator.main:app|8014"
  "archive|agents.archive.main:app|8020"
  "workflow_orchestrator|agents.workflow_orchestrator.main:app|8023"
)

# Explicitly set ARCHIVE_AGENT_PORT to match the launch port
export ARCHIVE_AGENT_PORT=8020
export WORKFLOW_ORCHESTRATOR_PORT=8023

PIDS=()

activate_conda_env() {
  # Use conda run in commands below; this function is a placeholder for future activation.
  return 0
}

# Check whether a TCP port is currently listening on localhost
is_port_in_use() {
  local port="$1"
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    return 0
  fi
  return 1
}

# Try to request a graceful shutdown on the given port by calling /shutdown
attempt_shutdown_port() {
  local port="$1"
  local url="http://localhost:${port}/shutdown"
  echo "Attempting graceful shutdown on port $port via $url"
  # Try POST then GET, with short timeout
  if command -v curl >/dev/null 2>&1; then
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST --max-time 3 "$url" || true)
    if [ "$code" = "200" ] || [ "$code" = "202" ] || [ "$code" = "204" ]; then
      echo "Shutdown endpoint accepted POST on $port (code $code)"
      return 0
    fi
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url" || true)
    if [ "$code" = "200" ] || [ "$code" = "202" ] || [ "$code" = "204" ]; then
      echo "Shutdown endpoint accepted GET on $port (code $code)"
      return 0
    fi
  fi
  return 1
}

# Kill processes holding a port. Attempts graceful TERM then SIGKILL if necessary.
free_port_force() {
  local port="$1"
  echo "Attempting to free port $port by killing process(es)"
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti tcp:"$port" || true)
  fi
  if [ -z "$pids" ]; then
    # Fallback to ss parsing for PID (format: users:("...",pid=1234,fd=3))
    pids=$(ss -ltnp 2>/dev/null | grep -E ":[.]?$port\b" | sed -n 's/.*pid=\([0-9]*\),.*/\1/p' | tr '\n' ' ')
  fi
  if [ -z "$pids" ]; then
    echo "No PID found for port $port; nothing to kill"
    return 1
  fi
  for pid in $pids; do
    echo "Sending TERM to pid $pid (port $port)"
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 3
  # Check if port still in use
  if is_port_in_use "$port"; then
    echo "Port $port still in use; sending SIGKILL to PIDs: $pids"
    for pid in $pids; do
      kill -9 "$pid" 2>/dev/null || true
    done
    sleep 1
  fi
  if is_port_in_use "$port"; then
    echo "Failed to free port $port"
    return 1
  fi
  echo "Port $port freed"
  return 0
}

# Parse optional args
DETACH=true  # Default to detach mode - services stay running
while [[ ${#} -gt 0 ]]; do
  case "$1" in
    --no-detach)
      DETACH=false
      shift
      ;;
    --health-timeout)
      HEALTH_TIMEOUT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--no-detach] [--health-timeout N]"
      echo "  --no-detach        Start agents and kill them when script exits (for testing)"
      echo "  --health-timeout N Override default health timeout in seconds (default: 10)"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

# Pre-flight: check ports 8000..8011 and attempt graceful shutdown if occupied

# Ensure MODEL_STORE_ROOT and per-agent caches point to the central data directory.
# Be resilient to the mountpoint case (Data vs data) or missing external drive after reboots.
if [ -d "/media/adra/Data" ]; then
  DEFAULT_BASE_MODELS_DIR="/media/adra/Data/justnews"
elif [ -d "/media/adra/data" ]; then
  DEFAULT_BASE_MODELS_DIR="/media/adra/data/justnews"
else
  # Fallback to a directory inside the user's home to avoid failures on systems
  # where the external data volume is not mounted. Operators can override via
  # the BASE_MODEL_DIR/MODEL_STORE_ROOT env vars before invoking the script.
  DEFAULT_BASE_MODELS_DIR="${HOME}/.local/share/justnews"
fi
export MODEL_STORE_ROOT="${MODEL_STORE_ROOT:-"$DEFAULT_BASE_MODELS_DIR/model_store"}"
export BASE_MODEL_DIR="${BASE_MODEL_DIR:-"$DEFAULT_BASE_MODELS_DIR/agents"}"

# Enforce strict ModelStore usage by default for production runs started via this script.
# Set STRICT_MODEL_STORE=0 to allow fallbacks for development/testing.
export STRICT_MODEL_STORE="${STRICT_MODEL_STORE:-1}"

# Primary database defaults: prefer MariaDB/MYSQL configuration. Postgres
# environment variables remain supported as a fallback for legacy systems
# but MariaDB is the default target moving forward.
export MARIADB_HOST="${MARIADB_HOST:-127.0.0.1}"
export MARIADB_PORT="${MARIADB_PORT:-3306}"
export MARIADB_DB="${MARIADB_DB:-justnews}"
export MARIADB_USER="${MARIADB_USER:-justnews}"
export MARIADB_PASSWORD="${MARIADB_PASSWORD:-justnews_password}"

# Mirror to JUSTNEWS_DB_* variables for scripts (e.g., news_outlets.py) if not explicitly set.
# Prefer MARIADB_* variables, else fall back to the legacy POSTGRES_* values for portability.
export JUSTNEWS_DB_HOST="${JUSTNEWS_DB_HOST:-${MARIADB_HOST:-${POSTGRES_HOST:-127.0.0.1}}}"
export JUSTNEWS_DB_PORT="${JUSTNEWS_DB_PORT:-${MARIADB_PORT:-${POSTGRES_PORT:-3306}}}"
export JUSTNEWS_DB_NAME="${JUSTNEWS_DB_NAME:-${MARIADB_DB:-${POSTGRES_DB:-justnews}}}"
export JUSTNEWS_DB_USER="${JUSTNEWS_DB_USER:-${MARIADB_USER:-${POSTGRES_USER:-justnews}}}"
export JUSTNEWS_DB_PASSWORD="${JUSTNEWS_DB_PASSWORD:-${MARIADB_PASSWORD:-${POSTGRES_PASSWORD:-justnews_password}}}"

# Per-agent cache envs (only set if not already set)
export SYNTHESIZER_MODEL_CACHE="${SYNTHESIZER_MODEL_CACHE:-"$DEFAULT_BASE_MODELS_DIR/agents/synthesizer/models"}"
export MEMORY_MODEL_CACHE="${MEMORY_MODEL_CACHE:-"$DEFAULT_BASE_MODELS_DIR/agents/memory/models"}"
export CHIEF_EDITOR_MODEL_CACHE="${CHIEF_EDITOR_MODEL_CACHE:-"$DEFAULT_BASE_MODELS_DIR/agents/chief_editor/models"}"
export FACT_CHECKER_MODEL_CACHE="${FACT_CHECKER_MODEL_CACHE:-"$DEFAULT_BASE_MODELS_DIR/agents/fact_checker/models"}"
export CRITIC_MODEL_CACHE="${CRITIC_MODEL_CACHE:-"$DEFAULT_BASE_MODELS_DIR/agents/critic/models"}"
export ANALYST_MODEL_CACHE="${ANALYST_MODEL_CACHE:-"$DEFAULT_BASE_MODELS_DIR/agents/analyst/models"}"
export SCOUT_MODEL_CACHE="${SCOUT_MODEL_CACHE:-"$DEFAULT_BASE_MODELS_DIR/agents/scout/models"}"
export REASONING_MODEL_CACHE="${REASONING_MODEL_CACHE:-"$DEFAULT_BASE_MODELS_DIR/agents/reasoning/models"}"

# Ensure directories exist (no sudo) and warn about permissions if not writable by current user
mkdir -p "$MODEL_STORE_ROOT" || true
for d in "$BASE_MODEL_DIR" "$SYNTHESIZER_MODEL_CACHE" "$MEMORY_MODEL_CACHE" "$CHIEF_EDITOR_MODEL_CACHE" "$FACT_CHECKER_MODEL_CACHE" "$CRITIC_MODEL_CACHE" "$ANALYST_MODEL_CACHE" "$SCOUT_MODEL_CACHE" "$REASONING_MODEL_CACHE"; do
  if [ ! -d "$d" ]; then
    mkdir -p "$d" 2>/dev/null || echo "WARNING: Could not create directory $d — check permissions"
  fi
  if [ ! -w "$d" ]; then
    echo "WARNING: $d is not writable by $(id -un). If agents need to download models here, adjust permissions or run as a user with access."
  fi
done

echo "Checking ports 8000..8025 for running agents..."
for port in $(seq 8000 8025); do
  if is_port_in_use "$port"; then
    echo "Port $port is currently in use. Attempting graceful shutdown..."
    if attempt_shutdown_port "$port"; then
      # Wait up to 10s for port to close
      deadline=$(( $(date +%s) + 10 ))
      while is_port_in_use "$port" && [ $(date +%s) -le $deadline ]; do
        sleep 1
      done
      if is_port_in_use "$port"; then
        echo "Shutdown endpoint did not free port $port in time; forcing kill"
        free_port_force "$port" || true
      else
        echo "Port $port freed by graceful shutdown"
      fi
    else
      echo "No shutdown endpoint or it failed for port $port; forcing kill"
      free_port_force "$port" || true
    fi
  fi
done

# ------------------------------------------------------------
# Optional pre-start sources seeding
# Enable by setting AUTO_SEED_SOURCES=1 (idempotent: only runs if table empty or missing)
# Requires: mysql (or mariadb) OR psql in PATH and scripts/news_outlets.py present.
# ------------------------------------------------------------
if [ "${AUTO_SEED_SOURCES:-0}" = "1" ]; then
  echo "[startup] AUTO_SEED_SOURCES=1 → attempting sources table seed"
  if command -v mysql >/dev/null 2>&1; then
    # Using mysql client to check MariaDB tables
    set +e
    SOURCE_COUNT=$(mysql --batch --silent -h $JUSTNEWS_DB_HOST -P $JUSTNEWS_DB_PORT -u $JUSTNEWS_DB_USER -p"$JUSTNEWS_DB_PASSWORD" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${JUSTNEWS_DB_NAME}' AND table_name='sources';" 2>/dev/null | tail -n1)
    STATUS=$?
    set -e
  elif command -v psql >/dev/null 2>&1; then
    set +e
    SOURCE_COUNT=$(psql "postgresql://$JUSTNEWS_DB_USER:$JUSTNEWS_DB_PASSWORD@$JUSTNEWS_DB_HOST:${JUSTNEWS_DB_PORT}/$JUSTNEWS_DB_NAME" -tAc "SELECT count(*) FROM public.sources" 2>/dev/null)
    STATUS=$?
    set -e
  else
    echo "[startup] WARNING: mysql or psql not installed – cannot auto-seed sources"
    NEED_SEED=0
    STATUS=1
  fi
    # NOTE: The DB client used above has set SOURCE_COUNT and STATUS accordingly.
    if [ $STATUS -ne 0 ] || [ -z "$SOURCE_COUNT" ]; then
      echo "[startup] sources table absent or inaccessible – will attempt seed (creating table if necessary)"
      NEED_SEED=1
    elif [ "$SOURCE_COUNT" = "0" ]; then
      echo "[startup] sources table empty – will seed"
      NEED_SEED=1
    else
      echo "[startup] sources table already populated ($SOURCE_COUNT rows) – skip seeding"
      NEED_SEED=0
    fi
    if [ "${NEED_SEED:-0}" = "1" ]; then
      if [ -f "$SCRIPT_DIR/scripts/news_outlets.py" ]; then
        echo "[startup] Seeding sources from potential_news_sources.md"
        conda run --name "$CONDA_ENV" python "$SCRIPT_DIR/scripts/news_outlets.py" \
          --file "$SCRIPT_DIR/markdown_docs/agent_documentation/potential_news_sources.md" || echo "[startup] WARNING: source seeding script failed"
      else
        echo "[startup] WARNING: scripts/news_outlets.py not found – cannot seed sources"
      fi
    fi
fi

start_agent() {
  local name="$1" module="$2" port="$3"
  local out_log="$LOG_DIR/${name}.out.log"
  local err_log="$LOG_DIR/${name}.err.log"

  echo "Starting $name -> $module on port $port"
  # Start uvicorn via conda run so the right env is used. Run in background.
  conda run --name "$CONDA_ENV" uvicorn "$module" --host 0.0.0.0 --port "$port" --log-level info >"$out_log" 2>"$err_log" &
  local pid=$!
  PIDS+=("$pid")
  echo "$name started (pid $pid), logs: $out_log, $err_log"
}

wait_for_health() {
  local name="$1" port="$2"
  local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  local url="http://localhost:$port/health"
  # Custom health endpoints per agent (keep minimal logic here)
  case "$name" in
    mcp_bus)
      url="http://localhost:$port/agents" # list agents implies bus is ready
      ;;
    analytics)
      # Analytics dashboard exposes /api/health, not /health
      url="http://localhost:$port/api/health"
      ;;
  esac

  echo "Waiting for $name to become healthy at $url (timeout ${HEALTH_TIMEOUT}s)"
  local attempts=0
  while [ $(date +%s) -le $deadline ]; do
    attempts=$((attempts + 1))
    if curl -s --max-time 2 "$url" >/dev/null 2>&1; then
      echo "✅ $name is healthy (after ${attempts}s)"
      return 0
    fi
    # Show progress every 5 seconds for MCP Bus
    if [ "$name" = "mcp_bus" ] && [ $((attempts % 5)) -eq 0 ]; then
      echo "  ... still waiting for $name (${attempts}s elapsed)"
    fi
    sleep 1
  done
  echo "⚠️ WARNING: $name did not report healthy within ${HEALTH_TIMEOUT}s (tried $attempts times)"
  return 1
}

if [ "$DETACH" = false ]; then
  trap 'echo "Shutting down agents..."; for pid in "${PIDS[@]:-}"; do echo "Killing $pid"; kill "$pid" 2>/dev/null || true; done; exit 0' SIGINT SIGTERM EXIT
else
  echo "Running in detach mode: started agents will continue running after this script exits."
fi

echo "Starting agents using conda env: $CONDA_ENV"
for entry in "${AGENTS[@]}"; do
  IFS='|' read -r name module port <<< "$entry"
  start_agent "$name" "$module" "$port"
done

echo "All agents started; performing health checks"
echo "Waiting 3 seconds for services to initialize..."
sleep 3

ALL_OK=0
for entry in "${AGENTS[@]}"; do
  IFS='|' read -r name module port <<< "$entry"
  if ! wait_for_health "$name" "$port"; then
    ALL_OK=1
  fi
done

if [ $ALL_OK -eq 0 ]; then
  echo "✅ All agents reported healthy (or responded)"
else
  echo "⚠️ Some agents failed health checks; check logs under $LOG_DIR"
fi

if [ "$DETACH" = true ]; then
  echo "Start script completed in detach mode. Agents will keep running. Started PIDs: ${PIDS[*]}"
  echo "Use ./stop_services.sh to stop all agents when needed."
  # Do not kill agents; exit successfully
  exit 0
else
  echo "Start script completed in test mode. To stop all started agents, send SIGINT to this script or kill PIDs: ${PIDS[*]}"
fi