#!/usr/bin/env bash
# JustNews Agent Startup Script for DevContainer
# Starts all agents using uvicorn from the devcontainer environment

set -e
cd /app
LOG_DIR=${LOG_DIR:-logs}
mkdir -p "$LOG_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[⚠]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

PUBLISHER_ENABLED=${PUBLISHER_ENABLED:-1}
PUBLISHER_HOST=${PUBLISHER_HOST:-0.0.0.0}
PUBLISHER_PORT=${PUBLISHER_PORT:-8100}

# Activate virtualenv and load environment
if [ -f "/deps/.venv/bin/activate" ]; then
    source /deps/.venv/bin/activate
elif [ -f "/app/.venv/bin/activate" ]; then
    source /app/.venv/bin/activate
else
    log_warning "Virtualenv not found in standard locations"
fi

# Load environment variables and export them
if [ -f "global.env" ]; then
    log_info "Loading environment variables from global.env..."
    # Export variables from global.env, skipping comments and empty lines
    set -a
    source global.env
    set +a
else
    log_warning "global.env not found!"
fi

log_info "=========================================="
log_info "JustNews Agent Startup (DevContainer)"
log_info "=========================================="
log_info ""

# Array of agents: name|module:app|port|env_vars (optional)|workers (optional)
# Balanced workers to prevent RAM exhaustion (each worker ~1.2GB)
# Run the shim on 8018 and forward to docker fact-check backend published on 8003
log_info "Using mcp_fact_checker_server Shim..."
# Use port 8018 for the Shim to avoid conflict with the stuck container on 8003
FACT_CHECKER_CMD="fact_checker|agents.fact_checker.shim:app|8018|PORT=8018 FACT_CHECKER_EXTERNAL_URL=http://localhost:8003|1"

AGENTS=(
  "mcp_bus|agents.mcp_bus.main:app|8000||1"
  "chief_editor|agents.chief_editor.main:app|8001||1"
  "$FACT_CHECKER_CMD"
  "analyst|agents.analyst.main:app|8004|FACT_CHECKER_URL=http://localhost:8018|2"
  "synthesizer|agents.synthesizer.main:app|8005|EVIDENCE_AUDIT_BASE_URL=http://localhost:8000|2"
  "critic|agents.critic.main:app|8006||1"
  "memory|agents.memory.main:app|8007||1"
  "reasoning|agents.reasoning.main:app|8008||1"
  "newsreader|agents.newsreader.main:app|8009||1"
  "dashboard|agents.dashboard.main:app|8013||1"
  "analytics|agents.analytics.dashboard:analytics_app|8012||1"
  "gpu_orchestrator|agents.gpu_orchestrator.main:app|8014||1"
  "archive|agents.archive.main:app|8020|ARCHIVE_AGENT_PORT=8020|1"
  "workflow_orchestrator|agents.workflow_orchestrator.main:app|8023|WORKFLOW_ORCHESTRATOR_PORT=8023|1"
  "crawler|agents.crawler.main:app|8022||1"
  "crawler_control|agents.crawler_control.main:app|8016||1"
)

PIDS=()
STARTED_AGENTS=()
FAILED_AGENTS=()
PUBLISHER_PID=""
PUBLISHER_STARTED=0

log_info "Checking for existing processes on target ports..."
for entry in "${AGENTS[@]}"; do
  IFS='|' read -r name module port env_vars workers <<< "$entry"
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    log_warning "Port $port already in use (may be previous agent instance)"
  fi
done

if [ "$PUBLISHER_ENABLED" = "1" ]; then
  log_info ""
  log_info "Starting Django publisher website (port $PUBLISHER_PORT)..."
  if ss -ltn "sport = :$PUBLISHER_PORT" 2>/dev/null | grep -q LISTEN; then
    log_warning "Port $PUBLISHER_PORT already in use (publisher may already be running)"
    PUBLISHER_STARTED=1
  else
    publisher_startup_log="$LOG_DIR/publisher.startup.log"
    publisher_main_log="$LOG_DIR/publisher.log"
    publisher_cmd="python manage.py runserver $PUBLISHER_HOST:$PUBLISHER_PORT"

    if eval "$publisher_cmd > \"$publisher_startup_log\" 2>&1 &"
    then
      PUBLISHER_PID=$!
      PIDS+=("$PUBLISHER_PID")
      PUBLISHER_STARTED=1
      log_success "publisher started (PID: $PUBLISHER_PID) -> logs: $publisher_main_log (console: $publisher_startup_log)"
    else
      log_error "publisher failed to start"
    fi
  fi
fi

log_info ""
log_info "Starting ${#AGENTS[@]} agents..."
log_info ""

for entry in "${AGENTS[@]}"; do
  IFS='|' read -r name module port env_vars workers <<< "$entry"
  
  # Default workers to 1 if not specified
  workers=${workers:-1}
  
  log_info "Starting: $name (port $port, workers $workers)"
  
  # Build environment export
  agent_env=""
  if [ -n "$env_vars" ]; then
    agent_env="export $env_vars && "
  fi
  
  # Start agent in background
  startup_log="$LOG_DIR/${name}.startup.log"
  main_log="$LOG_DIR/${name}.log"
  
  # Use python -m common.agent_runner instead of direct uvicorn to ensure log rotation
  cmd="$agent_env python -m common.agent_runner $module --host 0.0.0.0 --port $port --workers $workers --log-level info --agent-name $name"

  if eval "$cmd > \"$startup_log\" 2>&1 &"
  then
    pid=$!
    PIDS+=("$pid")
    STARTED_AGENTS+=("$name:$port:$pid")
    log_success "$name started (PID: $pid) -> logs: $main_log (console: $startup_log)"
  else
    FAILED_AGENTS+=("$name")
    log_error "$name failed to start"
  fi
  
  # Small delay to avoid overwhelming the system
  sleep 0.3
done

log_info ""
log_info "=========================================="
log_info "Agents launched. Waiting 3 seconds for startup..."
log_info "=========================================="
sleep 3

# Health check function
check_agent_health() {
  local port=$1
  local name=$2
  local url="http://localhost:$port/docs"
  
  if timeout 2 curl -s "$url" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

log_info ""
log_info "Performing health checks..."
log_info ""

if [ "$PUBLISHER_ENABLED" = "1" ] && [ "$PUBLISHER_STARTED" = "1" ]; then
  if timeout 2 curl -s "http://localhost:$PUBLISHER_PORT/" >/dev/null 2>&1; then
    log_success "publisher (port $PUBLISHER_PORT): ✓ Responding"
  elif [ -n "$PUBLISHER_PID" ] && kill -0 "$PUBLISHER_PID" 2>/dev/null; then
    log_warning "publisher (port $PUBLISHER_PORT): ⏱ Starting (may still be initializing)"
  elif [ -z "$PUBLISHER_PID" ]; then
    log_success "publisher (port $PUBLISHER_PORT): ✓ Already running"
  else
    log_error "publisher (port $PUBLISHER_PORT): ✗ Process died"
  fi
fi

HEALTHY_COUNT=0
UNHEALTHY_AGENTS=()

for entry in "${STARTED_AGENTS[@]}"; do
  IFS=':' read -r name port pid <<< "$entry"
  
  if check_agent_health "$port" "$name"; then
    log_success "$name (port $port): ✓ Responding"
    ((HEALTHY_COUNT++))
  else
    # Check if process is still alive
    if kill -0 "$pid" 2>/dev/null; then
      log_warning "$name (port $port): ⏱ Starting (may still be initializing)"
      ((HEALTHY_COUNT++))
    else
      log_error "$name (port $port): ✗ Process died (PID: $pid)"
      UNHEALTHY_AGENTS+=("$name")
    fi
  fi
done

log_info ""
log_info "=========================================="
log_info "Startup Summary"
log_info "=========================================="
log_info "Total agents: $((${#STARTED_AGENTS[@]} + ${#FAILED_AGENTS[@]}))"
log_info "Started: ${#STARTED_AGENTS[@]}"
log_info "Healthy: $HEALTHY_COUNT"
log_info "Failed to start: ${#FAILED_AGENTS[@]}"
if [ "$PUBLISHER_ENABLED" = "1" ]; then
  if [ "$PUBLISHER_STARTED" = "1" ]; then
    log_info "Publisher: Started on http://localhost:$PUBLISHER_PORT"
  else
    log_warning "Publisher: Not started"
  fi
fi
log_info ""

if [ ${#FAILED_AGENTS[@]} -gt 0 ]; then
  log_warning "Failed agents:"
  for agent in "${FAILED_AGENTS[@]}"; do
    log_warning "  • $agent"
  done
  log_info ""
fi

if [ ${#UNHEALTHY_AGENTS[@]} -gt 0 ]; then
  log_warning "Agents not yet responding (may be initializing):"
  for agent in "${UNHEALTHY_AGENTS[@]}"; do
    log_warning "  • $agent (check logs)"
  done
  log_info ""
fi

log_info "Agent Status URLs shown above."
log_info ""
log_info "Log directory: $LOG_DIR"
log_info "View logs: tail -f $LOG_DIR/*.log"
log_info "View startup errors: tail -f $LOG_DIR/*.startup.log"
if [ "$PUBLISHER_ENABLED" = "1" ]; then
  log_info "Publisher URL: http://localhost:$PUBLISHER_PORT/"
fi
log_info ""
log_info "To stop all agents: pkill -f 'common.agent_runner'"
if [ "$PUBLISHER_ENABLED" = "1" ]; then
  log_info "To stop publisher: pkill -f 'manage.py runserver.*$PUBLISHER_PORT'"
fi
log_info ""

if [ ${#FAILED_AGENTS[@]} -eq 0 ]; then
  log_success "All agents launched successfully!"
  exit 0
else
  log_error "Some agents failed to start"
  exit 1
fi
