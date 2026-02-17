#!/bin/bash
# wait_for_mcp.sh - Wait for MCP Bus to be ready
# Used by systemd services to ensure MCP Bus is available before starting

set -euo pipefail

# Configuration
MCP_BUS_URL="${MCP_BUS_URL:-http://localhost:8000}"
MAX_WAIT_TIME="${MAX_WAIT_TIME:-300}"  # 5 minutes default
CHECK_INTERVAL="${CHECK_INTERVAL:-5}"   # 5 seconds default

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Check if MCP Bus is responding
check_mcp_bus() {
    local url="$1"

    # Try to connect to MCP Bus health endpoint
    if curl -s --max-time 10 --connect-timeout 5 \
           --retry 2 --retry-delay 1 \
           "$url/health" > /dev/null 2>&1; then
        return 0
    fi

    # Fallback: try basic connectivity to port 8000
    if timeout 5 bash -c "</dev/tcp/localhost/8000" 2>/dev/null; then
        return 0
    fi

    return 1
}

# Wait for MCP Bus with timeout
wait_for_mcp_bus() {
    local url="$1"
    local max_wait="$2"
    local interval="$3"
    local elapsed=0

    log_info "Waiting for MCP Bus at $url (max ${max_wait}s)..."

    while [[ $elapsed -lt $max_wait ]]; do
        if check_mcp_bus "$url"; then
            log_success "MCP Bus is ready!"
            return 0
        fi

        log_info "MCP Bus not ready yet... (${elapsed}s elapsed)"
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    log_error "Timeout waiting for MCP Bus after ${max_wait}s"
    return 1
}

# Show usage
show_usage() {
    cat << EOF
MCP Bus Wait Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -u, --url URL       MCP Bus URL (default: http://localhost:8000)
    -t, --timeout SEC   Maximum wait time in seconds (default: 300)
    -i, --interval SEC  Check interval in seconds (default: 5)
    -q, --quiet         Suppress output (for systemd use)
    -h, --help          Show this help message

DESCRIPTION:
    Waits for the MCP Bus to become available before proceeding.
    Used by systemd services to ensure proper startup order.

EXAMPLES:
    $0                          # Wait with defaults
    $0 -u http://localhost:8000 # Specify custom URL
    $0 -t 600 -i 10            # Wait up to 10 minutes, check every 10s
    $0 -q                      # Quiet mode for systemd

EXIT CODES:
    0 - MCP Bus is ready
    1 - Timeout or connection error
EOF
}

# Parse command line arguments
parse_args() {
    QUIET_MODE=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -u|--url)
                MCP_BUS_URL="$2"
                shift 2
                ;;
            -t|--timeout)
                MAX_WAIT_TIME="$2"
                shift 2
                ;;
            -i|--interval)
                CHECK_INTERVAL="$2"
                shift 2
                ;;
            -q|--quiet)
                QUIET_MODE=true
                shift
                ;;
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

    # Enable quiet mode if output is not a terminal (systemd)
    if [[ ! -t 1 ]] || [[ ! -t 2 ]]; then
        QUIET_MODE=true
    fi

    # Suppress output in quiet mode
    if [[ "$QUIET_MODE" == true ]]; then
        exec 1>/dev/null 2>/dev/null
    fi
}

# Main function
main() {
    parse_args "$@"

    if [[ "$QUIET_MODE" == false ]]; then
        echo "========================================"
        log_info "MCP Bus Wait Script"
        echo "========================================"
    fi

    if ! wait_for_mcp_bus "$MCP_BUS_URL" "$MAX_WAIT_TIME" "$CHECK_INTERVAL"; then
        exit 1
    fi

    exit 0
}

# Run main function
main "$@"
