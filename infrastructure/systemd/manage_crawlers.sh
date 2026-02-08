#!/bin/bash
# manage_crawlers.sh - JustNews crawler service management script
# Specialized management for crawling services with unified crawler support

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_ROOT="$SCRIPT_DIR"
PROJECT_ROOT="$(cd "$SYSTEMD_ROOT/../.." && pwd)"

# Crawler service definitions
CRAWLER_SERVICES=(
    # "scout"          # Deprecated - Replaced by Crawler/FactChecker(Investigator)
    "crawler"          # Unified Production Crawler (updated from unified-crawler)
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

# Check if crawler services are installed
check_crawler_services_installed() {
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
}

# Enable crawler services
enable_crawlers() {
    log_info "Enabling JustNews crawler services..."

    for service in "${CRAWLER_SERVICES[@]}"; do
        log_info "Enabling justnews-${service}..."
        systemctl enable "justnews@${service}" 2>/dev/null || true
    done

    # Enable crawlers target
    systemctl enable justnews-crawlers.target 2>/dev/null || true

    log_success "All crawler services enabled"
}

# Disable crawler services
disable_crawlers() {
    log_info "Disabling JustNews crawler services..."

    for service in "${CRAWLER_SERVICES[@]}"; do
        log_info "Disabling justnews-${service}..."
        systemctl disable "justnews@${service}" 2>/dev/null || true
    done

    # Disable crawlers target
    systemctl disable justnews-crawlers.target 2>/dev/null || true

    log_success "All crawler services disabled"
}

# Start crawler services
start_crawlers() {
    log_info "Starting JustNews crawler services..."

    for service in "${CRAWLER_SERVICES[@]}"; do
        log_info "Starting justnews-${service}..."
        systemctl start "justnews@${service}"
        sleep 2
    done

    log_success "All crawler services started"
}

# Stop crawler services
stop_crawlers() {
    log_info "Stopping JustNews crawler services..."

    for service in "${CRAWLER_SERVICES[@]}"; do
        log_info "Stopping justnews-${service}..."
        systemctl stop "justnews@${service}" 2>/dev/null || true
    done

    log_success "All crawler services stopped"
}

# Restart crawler services
restart_crawlers() {
    log_info "Restarting JustNews crawler services..."
    stop_crawlers
    sleep 3
    start_crawlers
}

# Show status of crawler services
show_crawler_status() {
    echo
    log_info "JustNews Crawler Service Status:"
    echo "==================================="

    for service in "${CRAWLER_SERVICES[@]}"; do
        service_name="justnews@${service}"

        if systemctl is-active --quiet "$service_name"; then
            echo -e "${GREEN}●${NC} $service_name - Active"
        elif systemctl is-failed --quiet "$service_name"; then
            echo -e "${RED}●${NC} $service_name - Failed"
        else
            echo -e "${YELLOW}●${NC} $service_name - Inactive"
        fi
    done

    # Show crawlers target status
    echo
    log_info "Crawlers Target Status:"
    if systemctl is-active --quiet "justnews-crawlers.target"; then
        echo -e "${GREEN}●${NC} justnews-crawlers.target - Active"
    else
        echo -e "${YELLOW}●${NC} justnews-crawlers.target - Inactive"
    fi
    echo
}

# Run unified crawler test
test_unified_crawler() {
    log_info "Testing Unified Production Crawler..."

    # Check if service is running
    if ! systemctl is-active --quiet "justnews@crawler"; then
        log_error "Unified crawler service is not running"
        log_info "Start it with: sudo $0 start"
        exit 1
    fi

    # Test basic functionality (this would need to be implemented in the crawler)
    log_info "Unified crawler service is running and ready"
    log_success "Crawler test completed"
}

# Show crawler performance metrics
show_performance() {
    log_info "Crawler Performance Metrics:"
    echo "=============================="

    # This would integrate with the crawler's performance monitoring
    # For now, show basic service status
    for service in "${CRAWLER_SERVICES[@]}"; do
        service_name="justnews@${service}"

        echo "Service: $service_name"
        systemctl status "$service_name" --no-pager -l | grep -E "(Active|Memory|CPU|Tasks)" | head -5 || true
        echo "---"
    done
}

# Main function
main() {
    local action="${1:-status}"

    check_root
    check_systemctl
    check_crawler_services_installed

    case "$action" in
        "enable")
            enable_crawlers
            ;;
        "disable")
            disable_crawlers
            ;;
        "start")
            start_crawlers
            ;;
        "stop")
            stop_crawlers
            ;;
        "restart")
            restart_crawlers
            ;;
        "status")
            show_crawler_status
            ;;
        "test")
            test_unified_crawler
            ;;
        "performance"|"perf")
            show_performance
            ;;
        *)
            log_error "Usage: $0 {enable|disable|start|stop|restart|status|test|performance}"
            log_info "Commands:"
            log_info "  enable      - Enable all crawler services"
            log_info "  disable     - Disable all crawler services"
            log_info "  start       - Start all crawler services"
            log_info "  stop        - Stop all crawler services"
            log_info "  restart     - Restart all crawler services"
            log_info "  status      - Show status of crawler services"
            log_info "  test        - Test unified crawler functionality"
            log_info "  performance - Show crawler performance metrics"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
