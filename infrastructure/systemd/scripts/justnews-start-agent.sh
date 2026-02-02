#!/bin/bash
# justnews-start-agent.sh - Standardized agent startup script
# Provides consistent startup behavior across all JustNews agents

set -euo pipefail

# Configuration
SCRIPT_NAME="$(basename "$0")"
AGENT_NAME="${1:-}"

# Optionally prime env from global file early for root resolution
if [[ -r "/etc/justnews/global.env" ]]; then
    # shellcheck source=/dev/null
    source "/etc/justnews/global.env"
fi

# Resolve project root robustly (WorkingDirectory -> JUSTNEWS_ROOT -> SERVICE_DIR -> script-relative -> fallback)
resolve_project_root() {
    # Helper: consider a directory a valid repo root only if it contains expected agent folders
    _is_valid_root() {
        local root="$1"
        [[ -d "$root/agents" ]] && [[ -d "$root/agents/gpu_orchestrator" ]] && [[ -d "$root/infrastructure/systemd" ]]
    }

    local cwd; cwd="$(pwd)"
    if _is_valid_root "$cwd"; then
        echo "$cwd"; return 0
    fi

    if [[ -n "${JUSTNEWS_ROOT:-}" ]] && _is_valid_root "$JUSTNEWS_ROOT"; then
        echo "$JUSTNEWS_ROOT"; return 0
    fi

    if [[ -n "${SERVICE_DIR:-}" ]]; then
        if _is_valid_root "$SERVICE_DIR"; then
            echo "$SERVICE_DIR"; return 0
        fi
        if _is_valid_root "$SERVICE_DIR/JustNews"; then
            echo "$SERVICE_DIR/JustNews"; return 0
        fi
    fi

    # Try two levels up from this script (useful when running from repo, not after install)
    local script_dir; script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local candidate; candidate="$(cd "$script_dir/../../.." && pwd)"
    if _is_valid_root "$candidate"; then
        echo "$candidate"; return 0
    fi

    # Final fallback: known path on this machine
    echo "${SERVICE_DIR:-$HOME/JustNews}"; return 0
}

PROJECT_ROOT="$(resolve_project_root)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate agent name
validate_agent_name() {
    local agent="$1"

    if [[ -z "$agent" ]]; then
        log_error "Agent name is required"
        log_info "Usage: $SCRIPT_NAME <agent_name>"
        log_info "Available agents: mcp_bus, chief_editor, fact_checker, analyst, synthesizer, critic, memory, reasoning, dashboard, analytics, archive, hitl_service, crawl4ai, gpu_orchestrator, crawler, crawler_control, workflow_orchestrator"
        exit 1
    fi

    # List of valid agents
    local valid_agents=(
        "mcp_bus"
        "chief_editor"
        # "scout" (Deprecated)
        "fact_checker"
        "analyst"
        "synthesizer"
        "critic"
        "memory"
        "reasoning"
        "newsreader"
        "dashboard"
        "analytics"
        "archive"
        "hitl_service"
        "crawl4ai"
        "gpu_orchestrator"
        "crawler"
        "crawler_control"
        "workflow_orchestrator"
    )

    local agent_valid=false
    for valid_agent in "${valid_agents[@]}"; do
        if [[ "$agent" == "$valid_agent" ]]; then
            agent_valid=true
            break
        fi
    done

    if [[ "$agent_valid" == false ]]; then
        log_error "Invalid agent name: $agent"
        log_info "Valid agents: ${valid_agents[*]}"
        exit 1
    fi
}

# Check if agent directory exists
check_agent_directory() {
    local agent="$1"
    local agent_dir="$PROJECT_ROOT/agents/$agent"

    if [[ ! -d "$agent_dir" ]]; then
        log_error "Agent directory not found: $agent_dir"
        exit 1
    fi

    if [[ ! -f "$agent_dir/main.py" ]]; then
        log_error "Agent main script not found: $agent_dir/main.py"
        exit 1
    fi

    log_success "Agent directory and main script found"
}

# Setup environment
setup_environment() {
    local agent="$1"

    # Change to agent directory
    cd "$PROJECT_ROOT/agents/$agent"

    # Load global environment if available
    if [[ -f "/etc/justnews/global.env" ]]; then
        log_info "Loading global environment from /etc/justnews/global.env"
        set -a
        # shellcheck source=/dev/null
        source "/etc/justnews/global.env"
        set +a
    fi

    # Load agent-specific environment if available
    if [[ -f "/etc/justnews/${agent}.env" ]]; then
        log_info "Loading agent environment from /etc/justnews/${agent}.env"
        set -a
        # shellcheck source=/dev/null
        source "/etc/justnews/${agent}.env"
        set +a
    fi

    # Set default environment variables if not set
    export PYTHONPATH="${PYTHONPATH:-$PROJECT_ROOT}"
    export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

    # Safety mode: force CPU and conservative settings to avoid GPU-related hard resets
    if [[ "${SAFE_MODE:-false}" == "true" ]]; then
        export USE_GPU="false"
        # Disable CUDA visibility entirely for this process
        export CUDA_VISIBLE_DEVICES=""
        # Force CPU execution in libraries that check this flag
        export FORCE_CPU="1"
        # Make tokenizers single-threaded and reduce contention
        export TOKENIZERS_PARALLELISM="false"
        export OMP_NUM_THREADS="1"
        export MKL_NUM_THREADS="1"
        # Conservative PyTorch CUDA allocator config (harmless if CUDA disabled)
        export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True,max_split_size_mb:64,garbage_collection_threshold:0.6"
        # Disable embedding preloading to minimize memory spikes
        export EMBEDDING_PRELOAD_ENABLED="false"
        log_warning "SAFE_MODE enabled: GPU disabled and conservative settings applied"
    else
        # GPU-specific setup
        if [[ "${USE_GPU:-false}" == "true" ]]; then
            export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
            log_info "GPU mode enabled (CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES)"
            # Even with GPU, apply safer allocator defaults
            export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True,max_split_size_mb:128,garbage_collection_threshold:0.8}"
        fi
    fi

    # Auto-bootstrap canonical conda environment if desired and available.
    # This is idempotent and controlled by AUTO_BOOTSTRAP_CONDA (default: 1).
    if [[ "${AUTO_BOOTSTRAP_CONDA:-1}" == "1" ]]; then
        if command -v conda >/dev/null 2>&1; then
            local target_env="${CONDA_ENV:-${CANONICAL_ENV:-justnews-py312-phase1}}"
            if ! conda env list 2>/dev/null | awk '{print $1}' | grep -xq "$target_env"; then
                log_info "Conda env '$target_env' not found; running bootstrap (AUTO_BOOTSTRAP_CONDA=1)"
                # Run the idempotent bootstrap script; do not fail the agent startup if bootstrap fails
                if [[ -x "${PROJECT_ROOT}/scripts/bootstrap_conda_env.sh" ]]; then
                    "${PROJECT_ROOT}/scripts/bootstrap_conda_env.sh" --install-vllm-only || log_warning "Bootstrap script failed or was interrupted"
                else
                    log_warning "Bootstrap script not found at ${PROJECT_ROOT}/scripts/bootstrap_conda_env.sh"
                fi
            else
                log_info "Conda env '$target_env' already present; skipping bootstrap"
            fi
        else
            log_info "conda not available; skipping auto bootstrap"
        fi
    fi

    # Optionally install and enable Alertmanager systemd unit on central host.
    # Controlled by AUTO_INSTALL_ALERTMANAGER (default: 0). Only runs when starting the MCP Bus to
    # avoid multiple nodes attempting to manage the host-level systemd unit.
    if [[ "${AUTO_INSTALL_ALERTMANAGER:-0}" == "1" && "${agent}" == "mcp_bus" ]]; then
        if [[ -x "${PROJECT_ROOT}/scripts/install_alertmanager_unit.sh" ]]; then
            log_info "AUTO_INSTALL_ALERTMANAGER=1 and agent=mcp_bus: installing/enabling Alertmanager unit"
            # Run idempotent installer; do not fail startup if Alertmanager install fails.
            "${PROJECT_ROOT}/scripts/install_alertmanager_unit.sh" --enable || log_warning "Alertmanager unit installer failed or returned an error"
        else
            log_warning "Alertmanager installer script not found at ${PROJECT_ROOT}/scripts/install_alertmanager_unit.sh"
        fi
    fi

    log_success "Environment setup complete"
}

# Wait for dependencies
wait_for_dependencies() {
    local agent="$1"

    # MCP Bus wait: skip for mcp_bus and gpu_orchestrator, or when REQUIRE_BUS=0
    if [[ "${REQUIRE_BUS:-1}" != "0" && "$agent" != "mcp_bus" && "$agent" != "gpu_orchestrator" ]]; then
        log_info "Waiting for MCP Bus dependency..."

        if [[ -x "$PROJECT_ROOT/infrastructure/systemd/scripts/wait_for_mcp.sh" ]]; then
            if ! "$PROJECT_ROOT/infrastructure/systemd/scripts/wait_for_mcp.sh" -q; then
                log_error "Failed to connect to MCP Bus"
                exit 1
            fi
        else
            log_warning "MCP Bus wait script not found, proceeding anyway..."
        fi
    fi

    # Agent-specific dependencies
    case "$agent" in
        #"scout")
        #    # Scout may depend on memory agent
        #    ;;
        "analyst")
            # Analyst may depend on memory agent
            ;;
        "synthesizer")
            # Synthesizer depends on memory and analyst
            ;;
        "fact_checker")
            # Fact checker may depend on memory
            ;;
        "critic")
            # Critic depends on all analysis agents
            ;;
        "chief_editor")
            # Chief editor depends on all agents
            ;;
    esac

    log_success "Dependency check complete"
}

# Sanity check: ensure runtime python modules exist for this agent before launching.
# This is called from start_agent to produce clearer errors when venvs are misconfigured.
check_python_deps_and_exit_if_missing() {
    local agent="$1"
    # Resolve the python interpreter to use for dependency checks and startup.
    # Selection order (best-effort):
    # 1) explicit PYTHON_BIN from agent/global env
    # 2) explicit CANONICAL_PYTHON_PATH (if set and executable)
    # 3) default canonical env python path ($HOME/miniconda3/envs/${CANONICAL_ENV:-justnews-py312-phase1}/bin/python)
    # 4) if conda is present and env exists -> 'conda run -n <env> python'
    # 5) fallback to python3/python from PATH
    local py_cmd=""
    local conda_env_to_try="${CONDA_ENV:-${CANONICAL_ENV:-justnews-py312-phase1}}"

    # 1) explicit override
    if [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
        py_cmd="${PYTHON_BIN}"
    fi

    # 2) explicit canonical path variable
    if [[ -z "$py_cmd" && -n "${CANONICAL_PYTHON_PATH:-}" ]]; then
        if [[ -x "${CANONICAL_PYTHON_PATH}" ]]; then
            py_cmd="${CANONICAL_PYTHON_PATH}"
        else
            log_warning "CANONICAL_PYTHON_PATH='${CANONICAL_PYTHON_PATH}' is not executable; ignoring"
        fi
    fi

    # 3) try the default canonical env path
    if [[ -z "$py_cmd" ]]; then
        local default_canonical_path="$HOME/miniconda3/envs/${conda_env_to_try}/bin/python"
        if [[ -x "$default_canonical_path" ]]; then
            py_cmd="$default_canonical_path"
        fi
    fi

    # 4) fallback to conda run if conda exists and env is present
    if [[ -z "$py_cmd" ]] && command -v conda >/dev/null 2>&1; then
        if conda env list 2>/dev/null | awk '{print $1}' | grep -xq "$conda_env_to_try"; then
            py_cmd="conda run -n $conda_env_to_try python"
        fi
    fi

    # 5) last-resort PATH python
    if [[ -z "$py_cmd" ]]; then
        if command -v python3 >/dev/null 2>&1; then
            py_cmd="$(command -v python3)"
        elif command -v python >/dev/null 2>&1; then
            py_cmd="$(command -v python)"
        fi
    fi

    if [[ -z "$py_cmd" ]]; then
        log_warning "No usable python interpreter found; dependency validation will be skipped"
        return 0
    fi

    # Modules per agent (keep minimal to avoid import side-effects)
    local modules=(requests)
    if [[ "$agent" == "gpu_orchestrator" ]]; then
        modules=(requests uvicorn)
    fi
    if [[ "$agent" == "crawl4ai" ]]; then
        # Crawl4AI bridge requires uvicorn for serving and crawl4ai/aiohttp for crawling
        modules=(uvicorn crawl4ai aiohttp)
    fi
        if [[ "$agent" == "hitl_service" ]]; then
            modules=(uvicorn fastapi requests)
        fi
    if [[ "$agent" == "dashboard" ]]; then
        # Dashboard imports fastapi and uvicorn at module import time; ensure they exist
        modules=(uvicorn fastapi requests)
    fi

    # Auto-detect common modules in the agent's main script and add them to checks
    local agent_main_path="$PROJECT_ROOT/agents/${agent}/main.py"
    if [[ -f "$agent_main_path" ]]; then
        if grep -E "^\s*import[[:space:]]+uvicorn" "$agent_main_path" >/dev/null 2>&1 || grep -E "^\s*from[[:space:]]+uvicorn" "$agent_main_path" >/dev/null 2>&1; then
            modules+=(uvicorn)
        fi
        if grep -E "^\s*from[[:space:]]+fastapi[[:space:]]+import|^\s*import[[:space:]]+fastapi" "$agent_main_path" >/dev/null 2>&1; then
            modules+=(fastapi)
        fi
    fi

    local modules_var="${modules[*]}"
    local missing=""

    # Split the interpreter command for safe invocation (supports values like "conda run -n env python")
    local -a py_parts
    local IFS=' '
    read -r -a py_parts <<< "$py_cmd"
    if [[ ${#py_parts[@]} -eq 0 ]]; then
        log_error "Unable to resolve python command for dependency probe"
        exit 1
    fi

    # Run the dependency probe while suppressing errors from terminating the script under set -e
    set +e
    local probe_output
    probe_output="$(
        "${py_parts[@]}" - <<PYCODE 2>/dev/null
import sys
import importlib.util

mods = "${modules_var}".split()
missing = []
for name in mods:
    try:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    except Exception:
        missing.append(name)

sys.stdout.write(' '.join(missing))
PYCODE
    )"
    local probe_status=$?
    set -e

    if [[ $probe_status -ne 0 ]]; then
        log_warning "Dependency probe encountered an error (status=$probe_status); continuing"
    fi
    missing="$probe_output"

        if [[ -n "$missing" ]]; then
        log_error "Missing python modules for agent '$agent': $missing"
        if [[ "$py_cmd" == conda* ]]; then
            log_error "Install into the developer conda env (example): conda run -n ${conda_env_to_try} pip install $missing"
        else
            local py_path="$py_cmd"
            py_path="${py_path%% *}"
            log_error "Install them into the service venv (example): sudo ${py_path%/*}/pip install $missing"
        fi
        exit 1
    fi

    # Export the resolved python command so callers can reuse the same interpreter selection
    export SELECTED_PY_CMD="$py_cmd"
    # Provide a helpful warning if it's not the conda env python
    check_python_interpreter_is_conda || true
}

# If we detect the selected interpreter is not the canonical conda environment,
# warn about it to make debugging easier (does not change behavior).
check_python_interpreter_is_conda() {
    local cmd="${SELECTED_PY_CMD:-${PYTHON_BIN:-}}"
    local canonical_env="${CANONICAL_ENV:-justnews-py312-phase1}"
    local canonical_path="${CANONICAL_PYTHON_PATH:-$HOME/miniconda3/envs/${canonical_env}/bin/python}"

    if [[ -z "$cmd" ]]; then
        return 0
    fi

    # Consider the interpreter canonical if:
    # - it contains the conda env path (/envs/<env>/bin) OR
    # - it matches the canonical path explicitly OR
    # - it is a 'conda run -n <env> python' invocation
    if [[ "$cmd" == *"/envs/${canonical_env}/bin"* || "$cmd" == "$canonical_path" || "$cmd" == conda*"-n ${canonical_env}"* ]]; then
        return 0
    fi

    # Not canonical — warn the operator; optionally fail if strict enforcement is enabled
    log_warning "Selected python ($cmd) does not appear to be the developer conda env '${canonical_env}'"
    log_warning "If you intended to use the conda environment, set PYTHON_BIN or CANONICAL_PYTHON_PATH in /etc/justnews/global.env or enable PATH to include the conda env's bin"

    if [[ "${ENFORCE_CANONICAL_PYTHON:-0}" == "1" ]]; then
        log_error "ENFORCE_CANONICAL_PYTHON=1: refusing to continue with non-canonical interpreter: $cmd"
        exit 1
    fi
}

# Start the agent
start_agent() {
    local agent="$1"

    log_info "Starting $agent agent..."

    # Fail fast with actionable advice if runtime deps are missing in the chosen interpreter
    check_python_deps_and_exit_if_missing "$agent"

    # Build the command - use module invocation to fix relative imports
    # Prefer interpreter from env if provided; reuse the interpreter resolution from dependency check when possible
    local py_interpreter
    if [[ -n "${SELECTED_PY_CMD:-}" ]]; then
        py_interpreter="${SELECTED_PY_CMD}"
    else
        py_interpreter="${PYTHON_BIN:-python3}"
    fi
    local -a py_cmd_parts
    local IFS=' '
    read -r -a py_cmd_parts <<< "$py_interpreter"
    if [[ ${#py_cmd_parts[@]} -eq 0 ]]; then
        log_error "Resolved Python command is empty"
        exit 1
    fi
    local py_executable="${py_cmd_parts[0]}"
    if ! command -v "$py_executable" >/dev/null 2>&1; then
        log_warning "Configured PYTHON_BIN not found (PYTHON_BIN='${PYTHON_BIN:-}'), falling back to 'python3'"
        py_cmd_parts=("python3")
        py_executable="python3"
    fi
    local cmd
    if [[ "$agent" == "gpu_orchestrator" ]]; then
        # Prefer uvicorn runner for orchestrator for clearer server logs and binding
        local port="${GPU_ORCHESTRATOR_PORT:-8014}"
        if "${py_cmd_parts[@]}" -c "import uvicorn" >/dev/null 2>&1; then
            cmd=("${py_cmd_parts[@]}" "-m" "uvicorn" "agents.gpu_orchestrator.main:app" "--host" "0.0.0.0" "--port" "$port" "--log-level" "info")
            log_info "Using uvicorn runner on port $port"
        else
            log_warning "uvicorn not available; falling back to module runner"
            cmd=("${py_cmd_parts[@]}" "-m" "agents.${agent}.main")
        fi
    else
        cmd=("${py_cmd_parts[@]}" "-m" "agents.${agent}.main")
    fi

    # Add any additional arguments from environment
    if [[ -n "${AGENT_ARGS:-}" ]]; then
        # Split AGENT_ARGS into array (simple approach)
        IFS=' ' read -ra ARGS <<< "$AGENT_ARGS"
        cmd+=("${ARGS[@]}")
    fi

    # Log the command (without sensitive info)
    log_info "Using Python: $(command -v "$py_executable" || echo "$py_executable")"
    log_info "Executing: ${cmd[*]}"

    # Execute the agent
    exec "${cmd[@]}"
}

# Cleanup function
cleanup() {
    local exit_code=$?
    log_info "Agent startup script exiting with code $exit_code"
    exit $exit_code
}

# Show usage
show_usage() {
    cat << EOF
JustNews Agent Startup Script

USAGE:
    $0 <agent_name> [options]

AGENTS:
    mcp_bus         Central communication hub
    chief_editor    Workflow orchestration
    # scout           Content discovery (Deprecated, see crawler)
    fact_checker    Fact verification
    analyst         Sentiment analysis
    synthesizer     Content synthesis
    critic          Quality assessment
    memory          Data storage
    reasoning       Logical reasoning
    # newsreader      News processing (Deprecated)
    dashboard       Web interface
    analytics       System analytics and monitoring
    # balancer removed: responsibilities moved to critic/analytics/gpu_orchestrator
    archive         Content archiving and retrieval
    crawl4ai        Crawl4AI bridge (local HTTP crawler bridge)
    hitl_service    Human-in-the-loop labeling service (port 8040 by default)
    gpu_orchestrator GPU telemetry and allocation coordinator (SAFE_MODE-aware)
    crawler         Content crawling and data collection
    crawler_control Web interface for crawler management and monitoring
    workflow_orchestrator Workflow Orchestrator agent

OPTIONS:
    -h, --help      Show this help message

DESCRIPTION:
    Standardized startup script for all JustNews agents.
    Handles environment setup, dependency waiting, and agent execution.

EXAMPLES:
    $0 mcp_bus
    $0 scout
    $0 analyst --gpu

ENVIRONMENT:
    AGENT_ARGS      Additional arguments to pass to the agent
    USE_GPU         Enable GPU mode (default: false)
    CUDA_VISIBLE_DEVICES  GPU device selection
    PYTHON_BIN      Explicit interpreter to use for this agent (overrides selection)
    CANONICAL_PYTHON_PATH  Optional explicit canonical interpreter path to prefer
    ENFORCE_CANONICAL_PYTHON If set to 1, startup will fail unless interpreter resolves to the canonical env

EXIT CODES:
    0 - Success
    1 - Error
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 1 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Main function
main() {
    # Set up cleanup trap
    trap cleanup EXIT

    # Handle help first
    if [[ $# -eq 0 || "$1" == "-h" || "$1" == "--help" ]]; then
        show_usage
        exit 0
    fi

    local agent="$1"
    shift  # Remove agent name from arguments

    # Parse remaining arguments
    parse_args "$@"

    echo "========================================"
    log_info "JustNews Agent Startup: $agent"
    echo "========================================"

    log_info "Resolved PROJECT_ROOT=$PROJECT_ROOT"

    validate_agent_name "$agent"
    check_agent_directory "$agent"
    setup_environment "$agent"
    wait_for_dependencies "$agent"
    start_agent "$agent"
}

# Run main function with all arguments
main "$@"
