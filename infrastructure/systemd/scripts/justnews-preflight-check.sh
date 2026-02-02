#!/bin/bash
# justnews-preflight-check.sh - Pre-startup validation for JustNews services
set -euo pipefail

# Default configuration
GATE_ONLY=false
MCP_BUS_URL="${MCP_BUS_URL:-http://127.0.0.1:8000}"
GPU_ORCHESTRATOR_URL="${GPU_ORCHESTRATOR_URL:-http://127.0.0.1:8014}"
TIMEOUT=300 # 5 minutes for model preloading

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load global env if available so we can consult PYTHON_BIN for dependency checks
if [[ -f "/etc/justnews/global.env" ]]; then
    # shellcheck source=/dev/null
    set -a; source "/etc/justnews/global.env"; set +a
fi

# Helper paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Check that required Python modules are present for a given agent. This uses
# the configured PYTHON_BIN (if present) or falls back to system python. This
# mirrors the behavior used in deployment start scripts to provide consistent,
# actionable errors when venvs are missing packages.
check_agent_python_deps() {
    local agent="$1"
    # Prefer using a developer conda env when present (so checks match developer setup)
    local py_cmd=""
    local conda_env_to_try="${CONDA_ENV:-${CANONICAL_ENV:-justnews-py312-phase1}}"
    if command -v conda >/dev/null 2>&1; then
        if conda env list 2>/dev/null | awk '{print $1}' | grep -xq "$conda_env_to_try"; then
            py_cmd="conda run -n $conda_env_to_try python"
        fi
    fi
    if [[ -z "$py_cmd" ]]; then
    local py="${PYTHON_BIN:-$HOME/miniconda3/envs/${CANONICAL_ENV:-justnews-py312-phase1}/bin/python}"
        if [[ ! -x "$py" ]]; then
            py="$(command -v python3 || command -v python || true)"
        fi
        if [[ -z "$py" ]]; then
            log_warning "No Python interpreter found to perform dependency check; skipping"
            return 0
        fi
        py_cmd="$py"
    fi

    local req_mods
    case "$agent" in
        mcp_bus) req_mods=(requests) ;;
        gpu_orchestrator) req_mods=(requests uvicorn) ;;
        chief_editor) req_mods=(requests) ;;
        *) req_mods=(requests) ;;
    esac

    local modules_var="${req_mods[*]}"
    local missing
    missing=$(eval "$py_cmd - <<PYCODE 2>/dev/null
import importlib,sys
mods = \"${modules_var}\".split()
missing = [m for m in mods if importlib.util.find_spec(m) is None]
sys.stdout.write(' '.join(missing))
PYCODE
")

    if [[ -n "$missing" ]]; then
        log_error "Missing python modules for agent '$agent': $missing"
        if [[ "$py_cmd" == conda* ]]; then
            log_error "Install into the developer conda env (example): conda run -n ${conda_env_to_try} pip install $missing"
        else
            local py_path="$py_cmd"
            py_path="${py_path%% *}"
            log_error "Install them into the service venv (example): sudo ${py_path%/*}/pip install $missing"
        fi
        return 2
    fi
    log_success "Python dependencies present for agent '$agent'"
    return 0
}

# Parse arguments
for arg in "$@"; do
    case $arg in
        --gate-only)
        GATE_ONLY=true
        shift
        ;;
    esac
done

echo "========================================"
log_info "JustNews Preflight Check"
echo "========================================"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script should be run as root (sudo) for full validation"
    log_warning "Continuing with limited checks..."
fi

# Gate-only mode: for MCP Bus startup
if [ "$GATE_ONLY" = true ]; then
    log_info "Gate-only mode: ensuring gpu_orchestrator is up and models are ready"
    
    # 1. Wait for GPU Orchestrator to be healthy
    log_info "Waiting for GPU Orchestrator at $GPU_ORCHESTRATOR_URL..."
    start_time=$(date +%s)
    while true; do
        # Fetch health information so we can detect SAFE_MODE and avoid blocking
        health_response=$(curl -fsS "${GPU_ORCHESTRATOR_URL}/health" || true)
        if [[ -n "$health_response" ]]; then
            # If the orchestrator is running in SAFE_MODE we should not attempt
            # to trigger full model preloads (these are heavy and can fail) —
            # in that case allow gate-only checks to succeed quickly.
            safe_mode=$(echo "$health_response" | jq -r '.safe_mode // "false"' 2>/dev/null || echo "false")
            if [[ "$safe_mode" == "true" ]]; then
                log_warning "GPU Orchestrator is healthy and in SAFE_MODE — skipping model preload and allowing gated startup."
                log_success "Preflight (gate-only) passing because orchestrator SAFE_MODE is active."
                exit 0
            fi

            log_success "GPU Orchestrator is healthy."
            break
        fi
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [ $elapsed -ge $TIMEOUT ]; then
            log_error "Timeout waiting for GPU Orchestrator."
            exit 1
        fi
        sleep 5
    done

    # 2. Trigger and wait for model preloading
    # 0. Quick dependency sanity for the MCP Bus itself so we fail early
    log_info "Checking Python runtime dependencies for mcp_bus..."
    if ! check_agent_python_deps "mcp_bus"; then
        log_error "Dependency check failed for mcp_bus — aborting gate. See messages above."
        if [[ -x "$SCRIPT_DIR/ci_check_deps.py" || -f "$SCRIPT_DIR/ci_check_deps.py" ]]; then
            python3 "$SCRIPT_DIR/ci_check_deps.py" || true
        fi
        exit 1
    fi
    log_info "Triggering model preload via GPU Orchestrator..."
    preload_response=$(curl -s -X POST "${GPU_ORCHESTRATOR_URL}/models/preload" -H "Content-Type: application/json" -d '{"refresh": false}')
    
    if [[ $(echo "$preload_response" | jq -r '.all_ready') == "true" ]]; then
        log_success "Models were already preloaded."
        exit 0
    fi

    log_info "Waiting for model preloading to complete..."
    start_time=$(date +%s)
    while true; do
        status_response=$(curl -s "${GPU_ORCHESTRATOR_URL}/models/status")
        in_progress=$(echo "$status_response" | jq -r '.in_progress')
        
        if [[ "$in_progress" == "false" ]]; then
            failed_count=$(echo "$status_response" | jq -r '.summary.failed')
            if [[ $failed_count -gt 0 ]]; then
                log_error "Model preloading failed for $failed_count models."
                log_error "Details: $(echo "$status_response" | jq -c '.errors')"
                exit 1
            else
                log_success "All models preloaded successfully."
                break
            fi
        fi

        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [ $elapsed -ge $TIMEOUT ]; then
            log_error "Timeout waiting for model preloading."
            exit 1
        fi
        log_info "Preloading in progress... ($(echo "$status_response" | jq -r '.summary.done')/$(echo "$status_response" | jq -r '.summary.total'))"
        sleep 10
    done
    
    log_success "Preflight check (gate-only) passed."
    exit 0
fi

# Full preflight check (for other agents)
log_info "Full preflight mode: ensuring MCP Bus is ready"
log_info "Waiting for MCP Bus at $MCP_BUS_URL..."
start_time=$(date +%s)
while true; do
    if curl -fsS "${MCP_BUS_URL}/health" > /dev/null; then
        log_success "MCP Bus is healthy."
        break
    fi
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    if [ $elapsed -ge 60 ]; then
        log_error "Timeout waiting for MCP Bus."
        exit 1
    fi
    sleep 3
done

# Validate MariaDB connectivity (via helper if present)
if [[ -x "$SCRIPT_DIR/../helpers/db-check.sh" ]]; then
    log_info "Checking MariaDB via helper..."
    if ! "$SCRIPT_DIR/../helpers/db-check.sh"; then
        log_error "MariaDB connectivity check failed; aborting preflight."
        exit 1
    fi
else
    log_warning "MariaDB check helper not found; skipping DB validation."
fi

# Validate ChromaDB is reachable (if configured)
CHROMA_HOST="${CHROMADB_HOST:-localhost}"
CHROMA_PORT="${CHROMADB_PORT:-3307}"
log_info "Checking ChromaDB reachability at ${CHROMA_HOST}:${CHROMA_PORT}..."
if ! python3 - <<PY >/dev/null 2>&1
import socket, sys
try:
    sock = socket.socket()
    sock.settimeout(1)
    sock.connect(("${CHROMA_HOST}", int(${CHROMA_PORT})))
    sock.close()
except Exception:
    sys.exit(1)
sys.exit(0)
PY
then
    log_warning "Unable to reach ChromaDB at ${CHROMA_HOST}:${CHROMA_PORT}; some features may be degraded"
else
    log_success "ChromaDB appears reachable."
fi

# Validate local SQLite for HITL if enabled
HITL_DB_PATH="${HITL_DB_PATH:-agents/hitl_service/hitl_staging.db}"
if [[ "${ENABLE_HITL_PIPELINE:-false}" == "true" ]]; then
    log_info "Checking HITL SQLite DB path: ${HITL_DB_PATH}"
    mkdir -p "$(dirname "${HITL_DB_PATH}")" 2>/dev/null || true
    if ! touch "${HITL_DB_PATH}" 2>/dev/null; then
        log_error "Cannot create or write HITL DB path: ${HITL_DB_PATH}; aborting preflight."
        exit 1
    fi
    log_success "HITL SQLite DB path is writable: ${HITL_DB_PATH}"
fi

log_success "All preflight checks passed."
exit 0
