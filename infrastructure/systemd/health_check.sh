#!/bin/bash
# health_check.sh - JustNews service health monitoring script
# Performs comprehensive health checks on all JustNews services

set -uo pipefail  # Note: set -e removed to allow graceful handling of service check failures

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Service definitions with ports and health endpoints
declare -A SERVICES=(
    ["mcp_bus"]="8000:/health"
    ["chief_editor"]="8001:/health"
    # ["scout"]="8002:/health" (Deprecated)
    ["fact_checker"]="8003:/health"
    ["analyst"]="8004:/health"
    ["synthesizer"]="8005:/health"
    ["critic"]="8006:/health"
    ["memory"]="8007:/health"
    ["reasoning"]="8008:/health"
    ["newsreader"]="8009:/health"
    ["analytics"]="8012:/health"      # Analytics agent
    ["archive"]="8020:/health"        # Archive agent
    ["dashboard"]="8013:/health"      # Dashboard web UI
    ["gpu_orchestrator"]="8014:/health" # GPU Orchestrator service
    ["crawler"]="8015:/health"          # Unified Production Crawler instance
    ["crawler_control"]="8016:/"        # Crawler Control web interface
    ["workflow_orchestrator"]="8023:/health" # Workflow Orchestrator
    # Observability Stack
    ["prometheus"]="9090:/-/healthy:justnews-prometheus"
    ["grafana"]="3000:/api/health:justnews-grafana"
    ["node_exporter"]="9100:/:justnews-node-exporter"
    ["otel_node"]="8889:/metrics:justnews-otel-node"
    ["otel_central"]="8890:/metrics:justnews-otel-central"
)

# Additional readiness endpoints (service:port:/ready) for stricter gating
declare -A READINESS_ENDPOINTS=(
    ["gpu_orchestrator"]="8014:/ready"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TIMEOUT=10
HOST="localhost"
EXIT_CODE=0
PANEL=false
REFRESH=2

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

# Check if a port is listening
check_port() {
    local port="$1"
    local timeout="${2:-5}"

    if timeout "$timeout" bash -c "</dev/tcp/$HOST/$port" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Check HTTP endpoint
check_http_endpoint() {
    local port="$1"
    local endpoint="$2"
    local timeout="${3:-$TIMEOUT}"

    local url="http://$HOST:$port$endpoint"

    if command -v curl &> /dev/null; then
        if curl -s --max-time "$timeout" --fail "$url" >/dev/null 2>&1; then
            return 0
        fi
    elif command -v wget &> /dev/null; then
        if wget -q --timeout="$timeout" --tries=1 -O /dev/null "$url" 2>/dev/null; then
            return 0
        fi
    else
        log_warning "Neither curl nor wget found. Cannot check HTTP endpoints."
        return 1
    fi

    return 1
}

# Check systemd service status
check_service_status() {
    local service="$1"

    if systemctl is-active --quiet "justnews@${service}"; then
        echo "active"
    elif systemctl is-failed --quiet "justnews@${service}"; then
        echo "failed"
    else
        echo "inactive"
    fi
}

# Check individual service
check_service() {
    local service="$1"
    local port_endpoint="$2"

    local port endpoint service_override
    IFS=':' read -r port endpoint service_override <<< "$port_endpoint"

    local systemd_service_name="justnews@${service}"
    if [[ -n "$service_override" ]]; then
        systemd_service_name="$service_override"
    fi

    local service_status="unknown"
    local port_status="unknown"
    local http_status="unknown"

    # Check systemd service status (handle errors gracefully)
    if systemctl is-active --quiet "${systemd_service_name}" 2>/dev/null; then
        service_status="active"
    elif systemctl is-failed --quiet "${systemd_service_name}" 2>/dev/null; then
        service_status="failed"
    else
        service_status="inactive"
    fi

    # Prefer HTTP health for listening/healthy detection
    if curl -s --max-time 2 --fail "http://$HOST:$port$endpoint" >/dev/null 2>&1; then
        port_status="listening"
        http_status="healthy"
    else
        # Fallback to TCP port check
        if timeout 2 bash -c "</dev/tcp/$HOST/$port" 2>/dev/null; then
            port_status="listening"
        else
            port_status="not_listening"
        fi
    fi

    # If not already determined healthy, check HTTP endpoint
    if [[ "$port_status" == "listening" && "$http_status" == "unknown" ]]; then
        if curl -s --max-time 5 --fail "http://$HOST:$port$endpoint" >/dev/null 2>&1; then
            http_status="healthy"
        else
            http_status="unhealthy"
        fi
    fi

    # Determine overall status
    local overall_status="unknown"
    if [[ "$service_status" == "active" && "$port_status" == "listening" && "$http_status" == "healthy" ]]; then
        overall_status="healthy"
    elif [[ "$service_status" == "failed" ]]; then
        overall_status="failed"
    elif [[ "$service_status" == "inactive" ]]; then
        overall_status="stopped"
    else
        overall_status="degraded"
    fi

    # Output results
    local readiness_status="n/a"
    if [[ -v READINESS_ENDPOINTS[$service] && "$overall_status" == "healthy" ]]; then
        IFS=':' read -r rport rendpoint <<< "${READINESS_ENDPOINTS[$service]}"
        if curl -s --max-time 5 --fail "http://$HOST:$rport$rendpoint" >/dev/null 2>&1; then
            readiness_status="ready"
        else
            readiness_status="not_ready"
            if [[ "$overall_status" == "healthy" ]]; then
                overall_status="degraded"
            fi
        fi
    fi

    printf "%-18s %-9s %-12s %-12s %-10s %-10s\n" \
           "$service" "$overall_status" "$service_status" "$port_status" "$http_status" "$readiness_status"

    # Return status for exit code
    case "$overall_status" in
        "healthy")
            return 0
            ;;
        "failed")
            return 1
            ;;
        *)
            return 2  # Warning/degraded
            ;;
    esac
}

# Show usage
show_usage() {
    cat << EOF
JustNews Health Check Script

USAGE:
    $0 [OPTIONS] [SERVICES...]

OPTIONS:
    -h, --help          Show this help message
    -v, --verbose       Verbose output
    -t, --timeout SEC   Timeout for HTTP checks (default: 10)
    --host HOST         Host to check (default: localhost)
    --panel             Open an info panel (auto-refresh) in a separate terminal if possible
    --refresh SEC       Panel refresh interval (default: 2)

SERVICES:
    If no services specified, checks all services.
    Available services: ${!SERVICES[*]}

EXAMPLES:
    $0                          # Check all services
    $0 mcp_bus scout            # Check specific services
    $0 --timeout 5              # Use 5 second timeout
    $0 --host 192.168.1.100     # Check remote host

EXIT CODES:
    0 - All services healthy
    1 - One or more services failed
    2 - One or more services degraded/warning
EOF
}

# Parse command line arguments
parse_args() {
    VERBOSE=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            --host)
                HOST="$2"
                shift 2
                ;;
            --panel)
                PANEL=true
                shift
                ;;
            --refresh)
                REFRESH="$2"
                shift 2
                ;;
            *)
                break
                ;;
        esac
    done

    # Remaining arguments are service names
    if [[ $# -gt 0 ]]; then
        CHECK_SERVICES=("$@")
    else
        CHECK_SERVICES=("${!SERVICES[@]}")
    fi
}

open_panel() {
    # Build the command to watch
    local hc_path="$SCRIPT_DIR/health_check.sh"
    local base_cmd=("watch" "-n" "$REFRESH" "$hc_path" "-v")
    # Respect custom host or timeout in the watched command
    [[ -n "$HOST" ]] && base_cmd+=("--host" "$HOST")
    [[ -n "$TIMEOUT" ]] && base_cmd+=("-t" "$TIMEOUT")

    # If specific services were requested, include them
    if [[ ${#CHECK_SERVICES[@]} -gt 0 && ${#CHECK_SERVICES[@]} -ne ${#SERVICES[@]} ]]; then
        base_cmd+=("${CHECK_SERVICES[@]}")
    fi

    # Prefer desktop terminal emulators
    local term_cmd=""
    if command -v x-terminal-emulator >/dev/null 2>&1; then
        term_cmd=("x-terminal-emulator" "-e" "bash" "-lc" "${base_cmd[*]} ; exec bash")
    elif command -v gnome-terminal >/dev/null 2>&1; then
        term_cmd=("gnome-terminal" "--" "bash" "-lc" "${base_cmd[*]} ; exec bash")
    elif command -v konsole >/dev/null 2>&1; then
        term_cmd=("konsole" "-e" "bash" "-lc" "${base_cmd[*]} ; exec bash")
    elif command -v xfce4-terminal >/dev/null 2>&1; then
        term_cmd=("xfce4-terminal" "-e" "bash -lc '${base_cmd[*]} ; exec bash'")
    elif command -v xterm >/dev/null 2>&1; then
        term_cmd=("xterm" "-e" "bash" "-lc" "${base_cmd[*]} ; exec bash")
    fi

    if [[ -n "${term_cmd[*]:-}" ]]; then
        "${term_cmd[@]}" >/dev/null 2>&1 &
        exit 0
    fi

    # Tmux fallback (new window) if inside a tmux session
    if command -v tmux >/dev/null 2>&1 && [[ -n "${TMUX:-}" ]]; then
        tmux new-window -n "health" "${base_cmd[*]}"
        exit 0
    fi

    # Last resort: run watch inline
    exec "${base_cmd[@]}"
}

# Main function
main() {
    parse_args "$@"

    if [[ "$PANEL" == true ]]; then
        # Require watch
        if ! command -v watch >/dev/null 2>&1; then
            log_error "'watch' not found; install procps (Debian/Ubuntu) or iproute2 tools"
            exit 1
        fi
        open_panel
        return 0
    fi

    if [[ "$VERBOSE" == true ]]; then
        log_info "Checking services on $HOST with ${TIMEOUT}s timeout"
        echo
    fi

    # Header
    printf "%-18s %-9s %-12s %-12s %-10s %-10s\n" "SERVICE" "STATUS" "SYSTEMD" "PORT" "HTTP" "READY"
    echo "-------------------------------------------------------------------------------"

    local failed_count=0
    local warning_count=0
    local total_count=0

    # Check each service
    for service in "${CHECK_SERVICES[@]}"; do
        if [[ -v SERVICES[$service] ]]; then
            ((total_count++))
            # Capture exit code without triggering set -e
            check_service "$service" "${SERVICES[$service]}"
            local status_code=$?
            if [[ $status_code -eq 0 ]]; then
                : # Healthy
            elif [[ $status_code -eq 1 ]]; then
                ((failed_count++))
            elif [[ $status_code -eq 2 ]]; then
                ((warning_count++))
            fi
        else
            log_warning "Unknown service: $service"
        fi
    done

    echo
    echo "Summary:"
    echo "========"
    echo "Total services checked: $total_count"
    echo "Failed services: $failed_count"
    echo "Warning services: $warning_count"
    echo "Healthy services: $((total_count - failed_count - warning_count))"

    # Set exit code
    if [[ $failed_count -gt 0 ]]; then
        EXIT_CODE=1
    elif [[ $warning_count -gt 0 ]]; then
        EXIT_CODE=2
    else
        EXIT_CODE=0
    fi

    if [[ "$VERBOSE" == true ]]; then
        case $EXIT_CODE in
            0)
                log_success "All services are healthy!"
                ;;
            1)
                log_error "$failed_count service(s) failed!"
                ;;
            2)
                log_warning "$warning_count service(s) have warnings!"
                ;;
        esac
    fi

    return $EXIT_CODE
}

# Run main function
main "$@"
