#!/bin/bash
# enable_all.sh - JustNews systemd service management script
# Enables, disables, starts, and stops all JustNews services in proper order

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$SYSTEMD_ROOT/../.." && pwd)"

# Service definitions in startup order
SERVICES=(
    "gpu_orchestrator" # GPU Orchestrator (port 8014) — MUST start before mcp_bus
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
    "training_system"
    "analytics"      # Analytics service (port 8012 per canonical mapping)
    "archive"        # Archive agent (port 8012)
    "dashboard"      # Dashboard agent (port 8013)
    "hitl_service"   # Human-in-the-loop labeling service (port 8040)
    "crawl4ai"       # Crawl4AI bridge service (local HTTP bridge)
    "crawler"        # Unified Production Crawler - intelligent multi-strategy
    "crawler_control" # Crawler Control web interface (port 8016)
    "workflow_orchestrator" # Workflow Orchestrator (port 8020)
)

# Observability services (started before agents, stopped after)
# These run as independent units: justnews-<name>.service
OBSERVABILITY_SERVICES=(
    "otel-central"
    "otel-node"
    "prometheus"
    "grafana"
    "node-exporter"
    "dcgm-exporter"
    "sensor-logger"
)

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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (sudo)"
        exit 1
    fi
}

# Check if systemctl is available
check_systemctl() {
    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl not found. This script requires systemd."
        exit 1
    fi
}

# Check if services are installed
check_services_installed() {
    # Check for systemd template file instead of individual service files
    if [[ ! -f "/etc/systemd/system/justnews@.service" ]]; then
        log_error "Missing systemd service template file"
        log_error "Please install the systemd unit template first:"
        log_error "  sudo cp $SYSTEMD_ROOT/units/justnews@.service /etc/systemd/system/"
        log_error "  sudo systemctl daemon-reload"
        exit 1
    fi

    # Check for required scripts
    if [[ ! -f "/usr/local/bin/justnews-start-agent.sh" ]]; then
        log_error "Missing justnews-start-agent.sh script"
        log_error "Please install the startup script:"
        log_error "  sudo cp $SYSTEMD_ROOT/scripts/justnews-start-agent.sh /usr/local/bin/"
        log_error "  sudo chmod +x /usr/local/bin/justnews-start-agent.sh"
        exit 1
    fi

    if [[ ! -f "/usr/local/bin/wait_for_mcp.sh" ]]; then
        log_error "Missing wait_for_mcp.sh script"
        log_error "Please install the MCP wait script:"
        log_error "  sudo cp $SYSTEMD_ROOT/scripts/wait_for_mcp.sh /usr/local/bin/"
        log_error "  sudo chmod +x /usr/local/bin/wait_for_mcp.sh"
        exit 1
    fi

    if [[ ! -f "/usr/local/bin/justnews-preflight-check.sh" ]]; then
        log_error "Missing justnews-preflight-check.sh script"
        log_error "Please install the preflight helper:"
        log_error "  sudo cp $SYSTEMD_ROOT/scripts/justnews-preflight-check.sh /usr/local/bin/"
        log_error "  sudo chmod +x /usr/local/bin/justnews-preflight-check.sh"
        exit 1
    fi
}

# Ensure operator PATH wrappers exist (best-effort, idempotent)
ensure_path_wrappers() {
    local pairs=(
        "/usr/local/bin/enable_all.sh|$SYSTEMD_ROOT/scripts/enable_all.sh"
        "/usr/local/bin/health_check.sh|$SYSTEMD_ROOT/scripts/health_check.sh"
    )
    for pair in "${pairs[@]}"; do
        IFS='|' read -r dst src <<<"$pair"
        if [[ -f "$src" && ! -x "$dst" ]]; then
            cp "$src" "$dst" && chmod +x "$dst" || true
        fi
    done
}

# Wait for service to be ready
wait_for_service() {
    local service="$1"
    local timeout="${2:-30}"
    local count=0

    log_info "Waiting for $service to be ready..."

    while [[ $count -lt $timeout ]]; do
        if systemctl is-active --quiet "justnews@${service}"; then
            log_success "$service is ready"
            return 0
        fi

        sleep 1
        ((count++))
    done

    log_warning "$service did not become ready within $timeout seconds"
    return 1
}

# Wait for an HTTP endpoint to become healthy
wait_for_http() {
    local url="$1"
    local timeout="${2:-30}"
    local count=0

    while [[ $count -lt $timeout ]]; do
        if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        ((count++))
    done
    return 1
}

# Enforce GPU Power Limit (300W)
enforce_gpu_power_limit() {
    if command -v nvidia-smi &> /dev/null; then
        log_info "Enforcing GPU power limit of 300W..."
        # Apply to all GPUs. '-pl 300' sets power limit to 300W.
        # We ignore errors in case some GPUs don't support it or if it's already set.
        if nvidia-smi -pl 300; then
             log_success "GPU power limit set to 300W"
        else
             log_warning "Failed to set GPU power limit (or not supported)"
        fi
    else
        log_warning "nvidia-smi not found, skipping power limit enforcement"
    fi
}

# Check for sufficient system memory for VS Code / IDE
check_system_memory() {
    log_info "Checking system memory availability..."
    
    # Required spare memory in MB (e.g., 4GB for VS Code + OS overhead)
    local REQUIRED_SPARE_MB=4096 
    
    if [[ -f /proc/meminfo ]]; then
        # Extract MemAvailable in kB
        local available_kb
        available_kb=$(grep -i 'MemAvailable' /proc/meminfo | awk '{print $2}')
        
        if [[ -n "$available_kb" ]]; then
            local available_mb=$((available_kb / 1024))
            log_info "Available system memory: ${available_mb}MB (Required spare: ${REQUIRED_SPARE_MB}MB)"
            
            if [[ "$available_mb" -lt "$REQUIRED_SPARE_MB" ]]; then
                log_warning "Low system memory detected! Less than ${REQUIRED_SPARE_MB}MB available."
                log_warning "This might cause OOM instability for the IDE (VS Code)."
                # We won't block startup, but we warn loudly.
                echo -e "${YELLOW}WARNING: Proceeding with low memory could lead to crashes.${NC}"
                sleep 2
            else
                log_success "System memory check passed"
            fi
        else
             log_warning "Could not determine MemAvailable from /proc/meminfo"
        fi
    else
        log_warning "/proc/meminfo not found, skipping memory check"
    fi
}

# Enable services
enable_services() {
    log_info "Enabling JustNews services..."

    # Enable observability stack first
    for service in "${OBSERVABILITY_SERVICES[@]}"; do
        if systemctl list-unit-files | grep -q "justnews-${service}.service"; then
           log_info "Enabling justnews-${service}..."
           systemctl enable "justnews-${service}" 2>/dev/null || true
        else
           log_warning "Service justnews-${service} not found, skipping enable."
        fi
    done

    for service in "${SERVICES[@]}"; do
        log_info "Enabling justnews@${service}..."
        systemctl enable "justnews@${service}" 2>/dev/null || true
    done

    log_success "All services enabled"
}

# Disable services
disable_services() {
    log_info "Disabling JustNews services..."

    # Disable main agents
    for service in "${SERVICES[@]}"; do
        log_info "Disabling justnews@${service}..."
        systemctl disable "justnews@${service}" 2>/dev/null || true
    done

    # Disable observability stack
    for service in "${OBSERVABILITY_SERVICES[@]}"; do
        log_info "Disabling justnews-${service}..."
        systemctl disable "justnews-${service}" 2>/dev/null || true
    done

    log_success "All services disabled"
}

# Start services in order
start_services() {
    log_info "Starting JustNews services in order..."

    # Pre-flight checks
    enforce_gpu_power_limit
    check_system_memory

    # 0) Observability Stack
    for service in "${OBSERVABILITY_SERVICES[@]}"; do
        if systemctl list-unit-files | grep -q "justnews-${service}.service"; then
            log_info "Starting justnews-${service}..."
            systemctl start "justnews-${service}"
            
            # Simple health check for these singleton services
            if ! systemctl is-active --quiet "justnews-${service}"; then
                 log_warning "justnews-${service} failed to become active immediately."
            fi
        else
            log_warning "Service justnews-${service} not found, skipping start."
        fi
    done

    # 1) GPU Orchestrator first
    log_info "Starting GPU Orchestrator (justnews@gpu_orchestrator)..."
    systemctl start "justnews@gpu_orchestrator"
    if ! wait_for_service "gpu_orchestrator" 60; then
        log_error "gpu_orchestrator did not become active in time. Aborting."
        return 1
    fi
    if ! wait_for_http "http://127.0.0.1:8014/ready" 120; then
        log_warning "gpu_orchestrator READY endpoint not ready within timeout; continuing cautiously"
    else
        log_success "gpu_orchestrator reports READY"
    fi
    
    # 2) MCP Bus next
    log_info "Starting MCP Bus (justnews@mcp_bus)..."
    systemctl start "justnews@mcp_bus"
    if ! wait_for_service "mcp_bus" 30; then
        log_error "MCP Bus failed to start. Aborting."
        return 1
    fi
    if ! wait_for_http "http://127.0.0.1:8000/health" 30; then
        log_warning "MCP Bus HTTP health not ready within timeout"
    fi

    # 3) Start remaining services
    for service in "${SERVICES[@]:2}"; do
        log_info "Starting justnews@${service}..."
        if ! systemctl start "justnews@${service}"; then
            log_warning "Failed to start justnews@${service} (systemctl returned error). Continuing sequence..."
        fi
        # After starting certain services, wait for their HTTP readiness to avoid race conditions
        case "$service" in
            "dashboard")
                # Wait for the dashboard /transparency/status endpoint
                if wait_for_http "http://127.0.0.1:8013/transparency/status" 30; then
                    log_success "Dashboard is ready"
                else
                    log_warning "Dashboard status endpoint invalid"
                fi
                ;;
        esac
    done

    log_success "All services started"
}

# Stop services in reverse order
stop_services() {
    log_info "Stopping JustNews services..."

    # Stop in reverse order (dependencies first)
    for ((i=${#SERVICES[@]}-1; i>=0; i--)); do
        service="${SERVICES[i]}"
        log_info "Stopping justnews@${service}..."
        systemctl stop "justnews@${service}" 2>/dev/null || true
    done

    # Stop observability stack
    for ((i=${#OBSERVABILITY_SERVICES[@]}-1; i>=0; i--)); do
        service="${OBSERVABILITY_SERVICES[i]}"
        if systemctl list-unit-files | grep -q "justnews-${service}.service"; then
            log_info "Stopping justnews-${service}..."
            systemctl stop "justnews-${service}" 2>/dev/null || true
        fi
    done

    log_success "All services stopped"
}

# Restart all services
restart_services() {
    log_info "Restarting all JustNews services..."
    stop_services
    sleep 3
    start_services
}

# Show status of all services
show_status() {
    echo
    log_info "JustNews Service Status:"
    echo "=========================="

    echo "--- Observability ---"
    for service in "${OBSERVABILITY_SERVICES[@]}"; do
        if systemctl list-units --all | grep -q "justnews-${service}.service"; then
            if systemctl is-active --quiet "justnews-${service}"; then
                echo -e "${GREEN}●${NC} justnews-${service} - Active"
            elif systemctl is-failed --quiet "justnews-${service}"; then
                echo -e "${RED}●${NC} justnews-${service} - Failed"
            else
                echo -e "${YELLOW}●${NC} justnews-${service} - Inactive"
            fi
        else
             echo -e "${YELLOW}●${NC} justnews-${service} - Not installed"
        fi
    done
    echo

    echo "--- Agents ---"
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "justnews@${service}"; then
            echo -e "${GREEN}●${NC} justnews@${service} - Active"
        elif systemctl is-failed --quiet "justnews@${service}"; then
            echo -e "${RED}●${NC} justnews@${service} - Failed"
        else
            echo -e "${YELLOW}●${NC} justnews@${service} - Inactive"
        fi
    done
    echo
}

# Fresh start (stop, disable, enable, start)
fresh_start() {
    log_info "Performing fresh start of all services..."

    # Stop all services
    stop_services
    sleep 2

    # Disable all services
    disable_services
    sleep 2

    # Enable all services
    enable_services
    sleep 2

    # Start all services
    start_services

    log_success "Fresh start completed"
}

# Main function
main() {
    local action="${1:-status}"
    # Backward-compat alias: allow "--fresh" as synonym for "fresh"
    if [[ "$action" == "--fresh" ]]; then
        action="fresh"
    fi

    check_root
    check_systemctl
    check_services_installed
    ensure_path_wrappers

    case "$action" in
        "enable")
            enable_services
            ;;
        "disable")
            disable_services
            ;;
        "start")
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "status")
            show_status
            ;;
        "fresh")
            fresh_start
            ;;
        *)
            log_error "Usage: $0 {enable|disable|start|stop|restart|status|fresh|--fresh} [services...]"
            log_info "Commands:"
            log_info "  enable   - Enable all services"
            log_info "  disable  - Disable all services"
            log_info "  start    - Start all services in order"
            log_info "  stop     - Stop all services"
            log_info "  restart  - Restart all services"
            log_info "  status   - Show status of all services"
            log_info "  fresh    - Fresh start (stop→disable→enable→start)"
            log_info "  --fresh  - Alias of 'fresh' (backward compatible)"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
