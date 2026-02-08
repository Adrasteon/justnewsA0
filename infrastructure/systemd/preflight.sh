#!/bin/bash
# preflight.sh - JustNews pre-deployment validation script
# Performs comprehensive checks before deploying JustNews services

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
STOP_MODE=false
EXIT_CODE=0
GATE_ONLY=false
GATE_INSTANCE=""
# Allow environment override for gate timeout (defaults to 180s)
GATE_TIMEOUT=${GATE_TIMEOUT:-180}
CANONICAL_ENV="${CANONICAL_ENV:-justnews-py312-phase1}"

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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script should be run as root (sudo) for full validation"
        log_warning "Continuing with limited checks..."
        echo
    fi
}

# Check required commands
check_commands() {
    local required_commands=("systemctl" "curl" "python3" "ss")
    local missing_commands=()

    log_info "Checking required commands..."

    for cmd in "${required_commands[@]}"; do
        if command -v "$cmd" &> /dev/null; then
            log_success "✓ $cmd found"
        else
            log_error "✗ $cmd not found"
            missing_commands+=("$cmd")
        fi
    done

    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${missing_commands[*]}"
        return 1
    fi

    log_success "All required commands available"
    return 0
}

# Check GPU and CUDA environment (optional, warnings only)
check_gpu_environment() {
    log_info "Checking GPU/CUDA environment (optional)..."

    if command -v nvidia-smi &> /dev/null; then
        local driver
        driver=$(nvidia-smi --query --display=CONFIG 2>/dev/null | grep -i "Driver Version" | awk -F': ' '{print $2}' | head -n1)
        if [[ -z "$driver" ]]; then
            driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1)
        fi
        log_success "✓ NVIDIA driver detected${driver:+ (driver $driver)}"

        # Basic GPU info
        local gpu_count
        gpu_count=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l | tr -d ' ')
        if [[ "$gpu_count" -gt 0 ]]; then
            log_info "  GPUs: $gpu_count"
            nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>/dev/null | while IFS= read -r line; do
                log_info "  - $line"
            done
        fi
    else
        log_warning "⚠ NVIDIA driver tools (nvidia-smi) not found. GPU checks skipped."
    fi

    # CUDA toolkit (optional)
    if command -v nvcc &> /dev/null; then
        local cuda_ver
        cuda_ver=$(nvcc --version 2>/dev/null | grep -oP 'release \K[0-9]+\.[0-9]+')
        log_success "✓ CUDA toolkit detected${cuda_ver:+ (CUDA $cuda_ver)}"
    else
        log_info "CUDA toolkit not found (ok if using only drivers/runtime)."
    fi

    # Attempt PyTorch CUDA probe via the standard env (optional)
    if command -v conda &> /dev/null; then
        if conda env list 2>/dev/null | grep -E "^\s*${CANONICAL_ENV}\s" > /dev/null; then
            local torch_probe
            if torch_probe=$(conda run -n "${CANONICAL_ENV}" python - <<'PY' 2>/dev/null
import json, sys
try:
    import torch
    out = {
        "torch_version": torch.__version__,
        "cuda_available": bool(getattr(torch, 'cuda', None) and torch.cuda.is_available()),
        "cuda_version": getattr(torch.version, 'cuda', None),
        "device_count": torch.cuda.device_count() if getattr(torch, 'cuda', None) else 0,
    }
    print(json.dumps(out))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
PY
); then
                if echo "$torch_probe" | grep -q '"error"'; then
                    log_warning "⚠ PyTorch probe reported: $torch_probe"
                else
                    log_success "✓ PyTorch probe: $torch_probe"
                fi
            else
                log_warning "⚠ Unable to run PyTorch probe in conda env ${CANONICAL_ENV}"
            fi
        else
            log_info "Conda env ${CANONICAL_ENV} not found; skipping PyTorch probe."
        fi
    else
        log_info "Conda not found; skipping PyTorch probe."
    fi

    return 0
}

# Check that expected conda env exists (warning only)
check_conda_env_exists() {
    log_info "Checking conda environment availability..."
    if command -v conda &> /dev/null; then
        if conda env list 2>/dev/null | grep -E "^\s*${CANONICAL_ENV}\s" > /dev/null; then
            log_success "✓ Conda env ${CANONICAL_ENV} exists"
        else
            log_warning "⚠ Conda env ${CANONICAL_ENV} not found"
        fi
    else
        log_warning "⚠ conda not found in PATH; ensure the runtime env is available"
    fi
    return 0
}

# Check systemd units are enabled (warning only)
check_systemd_enabled_status() {
    log_info "Checking systemd unit enablement (warning-only)..."
    local services=(
        "mcp_bus" "chief_editor" "fact_checker" "analyst" "synthesizer"
        "critic" "memory" "reasoning" "newsreader" "dashboard" "analytics" "archive"
    )
    for service in "${services[@]}"; do
        local unit="justnews@${service}.service"
        if systemctl list-unit-files | grep -q "^${unit}[[:space:]]"; then
            if systemctl is-enabled "$unit" &>/dev/null; then
                log_success "✓ $unit enabled"
            else
                log_warning "⚠ $unit not enabled"
            fi
        else
            # Presence is checked elsewhere; avoid duplicate errors here
            log_info "(info) $unit presence checked above"
        fi
    done
    return 0
}

# Check ulimits, swap, and tmp mount flags (warnings)
check_ulimits_and_swap() {
    log_info "Checking system limits and swap..."

    # Open files limit
    local nofile
    nofile=$(ulimit -n 2>/dev/null || echo "unknown")
    if [[ "$nofile" != "unknown" && "$nofile" -lt 65536 ]]; then
        log_warning "⚠ Open files limit is $nofile (recommended: 65536+)"
    else
        log_success "✓ Open files limit: $nofile"
    fi

    # Swap presence
    if command -v swapon &>/dev/null; then
        if swapon --show | tail -n +2 | wc -l | grep -q '^[1-9]'; then
            log_success "✓ Swap is enabled"
        else
            log_info "No swap detected (acceptable on tuned systems)"
        fi
    fi

    # /tmp mount flags
    if command -v findmnt &>/dev/null; then
        local tmp_opts
        tmp_opts=$(findmnt -no OPTIONS /tmp 2>/dev/null || true)
        if echo "$tmp_opts" | grep -q noexec; then
            log_warning "⚠ /tmp mounted with noexec; Python wheels/venvs may fail"
        else
            log_success "✓ /tmp mount options OK (${tmp_opts:-unknown})"
        fi
    fi

    return 0
}

# Check database configuration presence (warning-only)
check_database_config() {
    log_info "Checking database configuration (warning-only)..."
    local global_env="/etc/justnews/global.env"
    if [[ -f "$global_env" ]]; then
        local db_url
        db_url=$(grep -E '^(DATABASE_URL|JUSTNEWS_DB_URL)=' "$global_env" | tail -n1 | awk -F'=' '{print $2}')
        if [[ -n "$db_url" ]]; then
            if echo "$db_url" | grep -Eq '^postgres(ql)?://'; then
                log_success "✓ Database URL present in global.env"
            else
                log_warning "⚠ Database URL found but not recognized as Postgres URI"
            fi
        else
            log_info "No database URL found in global.env (Memory agent may use defaults)"
        fi
    else
        log_info "global.env not present; skipping DB check"
    fi
    return 0
}

# Check systemd services
check_systemd_services() {
    local services=(
        "mcp_bus"
        "chief_editor"
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
        "gpu_orchestrator"
    )

    log_info "Checking systemd service files..."

    for service in "${services[@]}"; do
        local service_file="/etc/systemd/system/justnews@${service}.service"

        if [[ -f "$service_file" ]]; then
            log_success "✓ justnews@${service}.service exists"
        else
            log_error "✗ justnews@${service}.service missing"
            log_info "  Expected at: $service_file"
            return 1
        fi
    done

    log_success "All systemd service files present"
    return 0
}

# Check environment files
check_environment_files() {
    log_info "Checking environment files..."

    local env_files=(
        "/etc/justnews/global.env"
        "/etc/justnews/mcp_bus.env"
    )

    local missing_files=()

    for env_file in "${env_files[@]}"; do
        if [[ -f "$env_file" ]]; then
            log_success "✓ $(basename "$env_file") exists"
        else
            log_warning "⚠ $(basename "$env_file") missing (optional)"
            missing_files+=("$env_file")
        fi
    done

    if [[ ${#missing_files[@]} -eq 0 ]]; then
        log_success "All critical environment files present"
    else
        log_info "Missing environment files: ${missing_files[*]}"
    log_info "These can be created from templates in infrastructure/systemd/examples/"
    fi

    return 0
}

# Check port availability
check_ports() {
    local ports=(
        8000 8001 8002 8003 8004 8005
        8006 8007 8008 8009 8010 8011
        8012 8013 8014 8015 8016
    )

    log_info "Checking port availability..."

    local occupied_ports=()

    for port in "${ports[@]}"; do
        if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
            occupied_ports+=("$port")
            log_warning "⚠ Port $port is already in use"
        else
            log_success "✓ Port $port is available"
        fi
    done

    if [[ ${#occupied_ports[@]} -gt 0 ]]; then
        if [[ "$STOP_MODE" == true ]]; then
            log_info "Stopping services using occupied ports..."
            stop_occupied_services "${occupied_ports[@]}"
        else
            log_warning "Some ports are occupied. Use --stop to automatically free them."
            return 1
        fi
    fi

    log_success "Port availability check completed"
    return 0
}

# Stop services using occupied ports
stop_occupied_services() {
    local ports=("$@")
    local services_to_stop=()

    # Map ports to services
    declare -A port_to_service=(
        ["8000"]="mcp_bus"
        ["8001"]="chief_editor"
        ["8002"]="scout"
        # ["8002"]="scout" # DEPRECATEDhecker"
        ["8004"]="analyst"
        ["8005"]="synthesizer"
        ["8006"]="critic"
        ["8007"]="memory"
        ["8008"]="reasoning"
        ["8009"]="newsreader"
        ["8011"]="dashboard"
    )

    for port in "${ports[@]}"; do
        if [[ -v port_to_service[$port] ]]; then
            services_to_stop+=("${port_to_service[$port]}")
        fi
    done

    if [[ ${#services_to_stop[@]} -gt 0 ]]; then
        log_info "Stopping services: ${services_to_stop[*]}"

        for service in "${services_to_stop[@]}"; do
            systemctl stop "justnews@${service}" 2>/dev/null || true
            log_info "Stopped justnews@${service}"
        done

        # Wait a moment for ports to free up
        sleep 3
        log_success "Services stopped and ports should now be available"
    fi
}

# Check Python environment
check_python_environment() {
    log_info "Checking Python environment..."

    # Check if Python 3.11+ is available
    if python3 --version 2>&1 | grep -q "Python 3\."; then
        local python_version
        python_version=$(python3 --version 2>&1 | grep -oP 'Python \K[0-9]+\.[0-9]+')

        if [[ "$(printf '%s\n' "$python_version" "3.11" | sort -V | head -n1)" == "3.11" ]]; then
            log_success "✓ Python $python_version available"
        else
            log_warning "⚠ Python $python_version found (3.11+ recommended)"
        fi
    else
        log_error "✗ Python 3 not found"
        return 1
    fi

    # Check if conda environment exists
    if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
        log_success "✓ Conda environment active: $CONDA_DEFAULT_ENV"
    else
        log_warning "⚠ No conda environment active"
        log_info "  Consider activating: conda activate ${CANONICAL_ENV}"
    fi

    return 0
}

# Check project structure
check_project_structure() {
    log_info "Checking project structure..."

    local required_files=(
        "agents/mcp_bus/main.py"
        # "agents/scout/main.py" (Deprecated)
        "agents/analyst/main.py"
        "agents/synthesizer/main.py"
        "start_services_daemon.sh"
    )

    local missing_files=()

    for file in "${required_files[@]}"; do
        if [[ -f "$PROJECT_ROOT/$file" ]]; then
            log_success "✓ $file exists"
        else
            log_error "✗ $file missing"
            missing_files+=("$file")
        fi
    done

    if [[ ${#missing_files[@]} -gt 0 ]]; then
        log_error "Missing critical files: ${missing_files[*]}"
        return 1
    fi

    log_success "Project structure is valid"
    return 0
}

# Check disk space
check_disk_space() {
    log_info "Checking disk space..."

    local required_space_gb=10
    local available_space

    # Get available space in GB
    available_space=$(df "$PROJECT_ROOT" | tail -1 | awk '{print int($4/1024/1024)}')

    if [[ $available_space -ge $required_space_gb ]]; then
        log_success "✓ ${available_space}GB available (required: ${required_space_gb}GB)"
    else
        log_warning "⚠ Only ${available_space}GB available (recommended: ${required_space_gb}GB+)"
    fi

    return 0
}

# Show usage
show_usage() {
    cat << EOF
JustNews Preflight Check Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -s, --stop              Stop services using occupied ports
    --no-color              Disable colored output
    --gate-only [INSTANCE]  Minimal gate mode for systemd ExecStartPre; optionally pass instance name (e.g., gpu_orchestrator)

DESCRIPTION:
    Performs comprehensive pre-deployment validation checks for JustNews.
    Use --stop to automatically free occupied ports before deployment.

EXAMPLES:
    $0                  # Run all checks
    $0 --stop           # Run checks and stop conflicting services
    $0 --no-color       # Run checks without colors

EXIT CODES:
    0 - All checks passed
    1 - Critical issues found
    2 - Warnings found
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -s|--stop)
                STOP_MODE=true
                shift
                ;;
            --gate-only)
                GATE_ONLY=true
                # Optional positional instance name
                if [[ ${2:-} != "" && ${2:-} != -* ]]; then
                    GATE_INSTANCE="$2"; shift 2
                else
                    shift
                fi
                ;;
            --no-color)
                RED=''
                GREEN=''
                YELLOW=''
                BLUE=''
                NC=''
                shift
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
wait_for_orchestrator() {
    # Wait for gpu_orchestrator to listen on 8014 (up to GATE_TIMEOUT seconds)
    local deadline=$(( $(date +%s) + GATE_TIMEOUT ))
    while [[ $(date +%s) -le $deadline ]]; do
        if ss -ltn "sport = :8014" 2>/dev/null | grep -q LISTEN; then
            return 0
        fi
        sleep 1
    done
    return 1
}

gate_models_only() {
    # In gate-only mode, we only ensure models are preloaded via the orchestrator.
    # If we're gating the orchestrator itself, skip and return success.
    if [[ "$GATE_INSTANCE" == "gpu_orchestrator" ]]; then
        log_info "Gate-only for gpu_orchestrator: skipping orchestrator-dependent checks"
        return 0
    fi

    log_info "Gate-only mode: ensuring gpu_orchestrator is up and models are ready"
    if ! wait_for_orchestrator; then
        log_error "gpu_orchestrator not listening on :8014 within ${GATE_TIMEOUT}s"
        return 1
    fi

    # Use explicit loopback to avoid any IPv6/hosts ambiguity
    local ORCH="http://127.0.0.1:8014"

    # If already ready, short-circuit success before triggering anything
    # Be tolerant of schema variations: treat missing in_progress as not blocking
    local status_json
    status_json=$(curl -s --max-time 5 "$ORCH/models/status" || true)
    if echo "$status_json" | grep -Eq '"all_ready"[[:space:]]*:[[:space:]]*true'; then
        log_success "Models already ready (short-circuit)"
        return 0
    fi

    # Trigger preload without refresh; then poll status until complete
    local preload_raw preload_http preload_body deadline backoff
    if ! command -v curl >/dev/null 2>&1; then
        log_error "curl not available for gate-only preload"
        return 1
    fi

    preload_raw=$(curl -s -X POST -H 'Content-Type: application/json' --max-time 5 \
        -d '{"refresh":false}' "$ORCH/models/preload" -w "\n%{http_code}" || true)
    preload_http=$(echo "$preload_raw" | tail -n1)
    preload_body=$(echo "$preload_raw" | sed '$d')
    if [[ "$preload_http" == "503" ]]; then
        log_error "Model preload reported failures (HTTP 503)"
        if command -v jq >/dev/null 2>&1; then
            echo "$preload_body" | jq -r '.detail.errors[]? | " - agent=\(.agent) model=\(.model) error=\(.error)"' || true
        fi
        return 1
    fi

    deadline=$(( $(date +%s) + GATE_TIMEOUT ))
    backoff=1
    while [[ $(date +%s) -le $deadline ]]; do
        status_json=$(curl -s --max-time 5 "$ORCH/models/status" || true)
        # Success if all_ready true regardless of in_progress presence
    if echo "$status_json" | grep -Eq '"all_ready"[[:space:]]*:[[:space:]]*true'; then
            log_success "All models preloaded and ready"
            return 0
        fi
        # If explicitly not in progress and not all_ready, it's a failure
    if echo "$status_json" | grep -Eq '"in_progress"[[:space:]]*:[[:space:]]*false'; then
            log_error "Model preload completed with failures"
            if command -v jq >/dev/null 2>&1; then
                echo "$status_json" | jq -r '.errors[]? | " - agent=\(.agent) model=\(.model) error=\(.error)"' || true
                echo "$status_json" | jq '.summary' || true
            else
                # Fallback concise summary
                echo "$status_json" | sed -E 's/\s+/ /g' | cut -c1-500
            fi
            return 1
        fi
        # Sleep using the current (possibly fractional) backoff and double it
        sleep "$backoff"
        if awk -v b="$backoff" 'BEGIN{ if (b < 8) exit 0; exit 1 }'; then
            backoff=$(awk -v b="$backoff" 'BEGIN{ printf "%.6f", b * 2 }')
        fi
    done
    # Timeout path: emit a brief summary and fail
    if command -v jq >/dev/null 2>&1; then
        echo "$status_json" | jq '.summary // {}' || true
    else
        echo "$status_json" | sed -E 's/\s+/ /g' | cut -c1-200
    fi
    log_error "Model preload did not finish within ${GATE_TIMEOUT}s"
    return 1
}

main() {
    parse_args "$@"

    echo "========================================"
    log_info "JustNews Preflight Check"
    echo "========================================"
    echo

    check_root

    # Minimal gate-only path for systemd ExecStartPre
    if [[ "$GATE_ONLY" == true ]]; then
        if gate_models_only; then
            exit 0
        else
            exit 1
        fi
    fi

    local checks_passed=0
    local checks_total=0

    # Run all checks
    local checks=(
    "check_commands"
        "check_systemd_services"
        "check_environment_files"
        "check_ports"
        "check_python_environment"
        "check_project_structure"
    "check_disk_space"
    "check_conda_env_exists"
    "check_gpu_environment"
    "check_systemd_enabled_status"
    "check_ulimits_and_swap"
    "check_database_config"
    )

    for check_func in "${checks[@]}"; do
        ((checks_total++))
        echo
        if $check_func; then
            ((checks_passed++))
        else
            EXIT_CODE=1
        fi
    done

    # After basic checks, if gpu_orchestrator target port 8014 is free or running, attempt model preload
    echo
    echo "----------------------------------------"
    log_info "Model Store preload via gpu_orchestrator"
    echo "----------------------------------------"
    PRELOAD_WARN=0
    SUMMARY_JSON=""
    # Determine if orchestrator is reachable
    if ss -ltn "sport = :8014" 2>/dev/null | grep -q LISTEN; then
        if command -v curl >/dev/null 2>&1; then
            # Kick off preload job (do not refresh if previous completed successfully)
            # Capture both body and HTTP status code
            PRELOAD_RAW=$(curl -s -X POST -H 'Content-Type: application/json' --max-time 5 \
                -d '{"refresh":false}' "http://localhost:8014/models/preload" -w "\n%{http_code}" || true)
            PRELOAD_HTTP=$(echo "$PRELOAD_RAW" | tail -n1)
            PRELOAD_BODY=$(echo "$PRELOAD_RAW" | sed '$d')
            if [[ -n "$PRELOAD_BODY" ]]; then
                if [[ "$PRELOAD_HTTP" == "503" ]]; then
                    log_error "Model preload reported failures (HTTP 503)"
                    if command -v jq >/dev/null 2>&1; then
                        # Extract and display error list
                        echo "$PRELOAD_BODY" | jq -r '.detail.errors[]? | " - agent=\(.agent) model=\(.model) error=\(.error)"' || true
                    else
                        # Show a compact fallback
                        echo "$PRELOAD_BODY" | sed -E 's/\s+/ /g' | cut -c1-300
                    fi
                    EXIT_CODE=1
                else
                    log_info "Preload job triggered on gpu_orchestrator (HTTP $PRELOAD_HTTP)"
                fi
                # Poll status up to 180s with exponential backoff
                DEADLINE=$(( $(date +%s) + 180 ))
                BACKOFF=1
                while [[ $(date +%s) -le $DEADLINE ]]; do
                    STATUS_JSON=$(curl -s --max-time 5 "http://localhost:8014/models/status" || true)
                    SUMMARY_JSON="$STATUS_JSON"
                    if echo "$STATUS_JSON" | grep -q '"in_progress": false'; then
                        # Completed; check all_ready
                        if echo "$STATUS_JSON" | grep -q '"all_ready": true'; then
                            log_success "All models preloaded and ready"
                            break
                        else
                            log_error "Model preload completed with failures"
                            # Print detailed errors if available
                            if command -v jq >/dev/null 2>&1; then
                                echo "$STATUS_JSON" | jq -r '.errors[]? | " - agent=\(.agent) model=\(.model) error=\(.error)"'
                                echo "$STATUS_JSON" | jq '.summary'
                            else
                                echo "$STATUS_JSON" | sed -E 's/\s+/ /g' | cut -c1-500
                            fi
                            EXIT_CODE=1
                            break
                        fi
                    else
                                # In progress; backoff up to 8s
                                echo -n "."
                                sleep "$BACKOFF"
                                if awk -v b="$BACKOFF" 'BEGIN{ if (b < 8) exit 0; exit 1 }'; then
                                    BACKOFF=$(awk -v b="$BACKOFF" 'BEGIN{ printf "%.6f", b * 2 }')
                                fi
                    fi
                done
                echo
                if [[ $(date +%s) -gt $DEADLINE ]]; then
                    # Timeout: if not all_ready, treat as non-zero exit (hard gate)
                    if echo "$STATUS_JSON" | grep -q '"all_ready": true'; then
                        log_success "Model preload eventually reported ready at timeout boundary"
                    else
                        log_error "Model preload did not finish within 180s; not all models ready"
                        EXIT_CODE=1
                    fi
                    PRELOAD_WARN=1
                fi
            else
                log_warning "Failed to trigger preload on gpu_orchestrator"
                PRELOAD_WARN=1
            fi
        else
            log_warning "curl not available; skipping model preload trigger"
            PRELOAD_WARN=1
        fi
    else
        log_warning "gpu_orchestrator (8014) not listening; skipping model preload"
        PRELOAD_WARN=1
    fi

    echo
    echo "========================================"
    echo "Preflight Summary:"
    echo "========================================"
    echo "Checks passed: $checks_passed/$checks_total"

    if [[ $checks_passed -eq $checks_total ]]; then
        log_success "🎉 All preflight checks passed!"
        log_info "Ready to deploy JustNews services."
        EXIT_CODE=0
    elif [[ $EXIT_CODE -eq 1 ]]; then
        log_error "❌ Critical issues found. Please resolve before deployment."
    else
        log_warning "⚠️ Some warnings found. Deployment may proceed but review issues."
        EXIT_CODE=2
    fi

    # If model preload step had warnings and exit code is still 0, downgrade to warnings
    if [[ "$PRELOAD_WARN" -eq 1 && $EXIT_CODE -eq 0 ]]; then
        log_warning "Model preload step reported warnings; adjusting exit code to 2"
        EXIT_CODE=2
    fi

    # Write concise JSON summary to cache
    CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/justnews/preflight"
    mkdir -p "$CACHE_DIR" || true
    TS="$(date +%Y%m%d_%H%M%S)"
    if [[ -n "$SUMMARY_JSON" ]]; then
        printf '{"timestamp":"%s","preload":"%s"}\n' "$TS" "$(echo "$SUMMARY_JSON" | tr -d '\n' | sed -E 's/"/\\"/g')" > "$CACHE_DIR/summary_${TS}.json"
        echo "ONE-LINE-PRELOAD-SUMMARY: {\"timestamp\":\"$TS\",\"all_ready\":$(echo "$SUMMARY_JSON" | grep -o '"all_ready": [^,]*' | awk -F': ' '{print $2}' | tr -d ' '),\"failed\":$(echo "$SUMMARY_JSON" | grep -o '"failed": [0-9]\\+' | awk -F': ' '{print $2}') }"
        log_info "Preload summary saved to $CACHE_DIR/summary_${TS}.json"
    fi
    echo
    if [[ "$STOP_MODE" == true ]]; then
        log_info "Stop mode was enabled - conflicting services were stopped."
    fi

    return $EXIT_CODE
}

# Run main function
main "$@"
