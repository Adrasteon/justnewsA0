#!/usr/bin/env bash
# JustNews Agent Startup Script for DevContainer
# Starts all agents using uvicorn from the devcontainer environment

set -e
cd /app

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

# Activate virtualenv and load environment
source /deps/.venv/bin/activate

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
if [ "$USE_EXTERNAL_FACT_CHECKER" == "true" ]; then
    log_info "Using External Fact Checker Shim..."
    # Point to the background process started on port 8011 for immediate usage
    FACT_CHECKER_CMD="fact_checker|agents.fact_checker.shim:app|8003|FACT_CHECKER_EXTERNAL_URL=http://localhost:8011|1"
else
    FACT_CHECKER_CMD="fact_checker|agents.fact_checker.main:app|8003||2"
fi

AGENTS=(
  "mcp_bus|agents.mcp_bus.main:app|8000||1"
  "chief_editor|agents.chief_editor.main:app|8001||1"
  "$FACT_CHECKER_CMD"
  "analyst|agents.analyst.main:app|8004||1"
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

log_info "Checking for existing processes on target ports..."
for entry in "${AGENTS[@]}"; do
  IFS='|' read -r name module port env_vars workers <<< "$entry"
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    log_warning "Port $port already in use (may be previous agent instance)"
  fi
done

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
  out_log="$LOG_DIR/${name}.log"
  err_log="$LOG_DIR/${name}.err"
  
  if eval "$agent_env uvicorn $module --host 0.0.0.0 --port $port --workers $workers --log-level info" > "$out_log" 2> "$err_log" &
  then
    pid=$!
    PIDS+=("$pid")
    STARTED_AGENTS+=("$name:$port:$pid")
    log_success "$name started (PID: $pid) → logs: $out_log"
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

log_info "Agent Status URLs:"
log_info "  mcp_bus:      http://localhost:8000/docs"
log_info "  chief_editor: http://localhost:8001/docs"
log_info "  fact_checker: http://localhost:8003/docs"
log_info "  analyst:      http://localhost:8004/docs"
log_info "  synthesizer:  http://localhost:8005/docs (requires EVIDENCE_AUDIT_BASE_URL)"
log_info "  critic:       http://localhost:8006/docs"
log_info "  memory:       http://localhost:8007/docs"
log_info "  reasoning:    http://localhost:8008/docs"
log_info "  newsreader:   http://localhost:8009/docs"
log_info "  dashboard:    http://localhost:8013/docs"
log_info "  analytics:    http://localhost:8012/docs"
log_info "  gpu_orchestrator: http://localhost:8014/docs"
log_info "  archive:      http://localhost:8020/docs"
log_info "  workflow_orchestrator: http://localhost:8023/docs"
log_info "  crawler:      http://localhost:8022/docs"
log_info "  crawler_control: http://localhost:8016/docs"
log_info ""
log_info "Log directory: $LOG_DIR"
log_info "View logs: tail -f $LOG_DIR/*.log"
log_info ""
log_info "To stop all agents: pkill -f 'uvicorn agents'"
log_info ""

if [ ${#FAILED_AGENTS[@]} -eq 0 ]; then
  log_success "All agents launched successfully!"
  exit 0
else
  log_error "Some agents failed to start"
  exit 1
fi
