#!/bin/bash
# Health Check Script for JustNews
# Validates deployment health across all platforms

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_ROOT="$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Global health status
HEALTH_STATUS="healthy"
FAILED_CHECKS=()

# Add failed check
add_failure() {
    FAILED_CHECKS+=("$1")
    HEALTH_STATUS="unhealthy"
}

# Service definitions
SERVICES=(
    "mcp-bus:8000"
    "chief-editor:8001"
    # "scout:8002"
    "fact-checker:8003"
    "analyst:8004"
    "synthesizer:8005"
    "critic:8006"
    "memory:8007"
    "reasoning:8008"
    "gpu-orchestrator:8014"
    "dashboard:8013"
)

# Check service health
check_service() {
    local service=$1
    local port=$2

    log_info "Checking $service on port $port..."

    if timeout 5 bash -c "echo > /dev/tcp/localhost/$port" 2>/dev/null; then
        if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
            log_success "$service is healthy"
            return 0
        elif curl -s -f "http://localhost:$port/" >/dev/null 2>&1; then
            log_success "$service is responding"
            return 0
        else
            log_warning "$service port open but no health endpoint"
            return 0
        fi
    else
        log_error "$service is not responding on port $port"
        add_failure "$service:port_$port"
        return 1
    fi
}

# Check systemd health
check_systemd() {
    log_info "Checking systemd deployment..."

    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl not available"
        add_failure "systemctl:unavailable"
        return 1
    fi

    local failed_services=0

    for service in /etc/systemd/system/justnews-*.service; do
        if [[ -f "$service" ]]; then
            local service_name=$(basename "$service")
            if ! systemctl is-active "$service_name" >/dev/null 2>&1; then
                log_error "Service $service_name is not active"
                add_failure "systemd:service_${service_name}"
                ((failed_services++))
            else
                log_success "Service $service_name is active"
            fi
        fi
    done

    if [[ $failed_services -gt 0 ]]; then
        return 1
    fi

    return 0
}

# Check database connectivity
check_database() {
    log_info "Checking database connectivity..."

    # Prefer MariaDB (mysql client) connectivity checks by default.
    if command -v mysql &> /dev/null; then
        if mysql --user="${MARIADB_USER:-${POSTGRES_USER:-justnews}}" --password="${MARIADB_PASSWORD:-${POSTGRES_PASSWORD:-}}" \
            --host="${MARIADB_HOST:-${POSTGRES_HOST:-localhost}}" --port="${MARIADB_PORT:-${POSTGRES_PORT:-3306}}" \
            -e "SELECT 1;" >/dev/null 2>&1; then
            log_success "MariaDB connection successful"
            return 0
        fi
    fi

    # Fall back to Postgres check if mysql not present
    if command -v psql &> /dev/null; then
        if PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" \
            -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-justnews}" \
            -d "${POSTGRES_DB:-justnews}" -c "SELECT 1;" >/dev/null 2>&1; then
            log_success "Postgres connection successful (legacy)"
            return 0
        fi
    fi

    log_error "Database connection failed"
    add_failure "database:connection_failed"
    return 1
}

# Check GPU availability
check_gpu() {
    log_info "Checking GPU availability..."

    if command -v nvidia-smi &> /dev/null; then
        local gpu_count
        gpu_count=$(nvidia-smi --list-gpus 2>/dev/null | wc -l)
        if [[ $gpu_count -gt 0 ]]; then
            log_success "GPU available: $gpu_count device(s)"
            return 0
        fi
    fi

    if curl -s -f "http://localhost:8014/health" >/dev/null 2>&1; then
        log_success "GPU orchestrator available"
        return 0
    fi

    log_warning "No GPU available - using CPU fallback"
    return 0
}

# Check monitoring stack
check_monitoring() {
    log_info "Checking monitoring stack..."

    if curl -s -f "http://localhost:9090/-/healthy" >/dev/null 2>&1; then
        log_success "Prometheus is healthy"
    else
        log_warning "Prometheus not available"
    fi

    if curl -s -f "http://localhost:3000/api/health" >/dev/null 2>&1; then
        log_success "Grafana is healthy"
    else
        log_warning "Grafana not available"
    fi
}

# Generate health report
generate_report() {
    log_info "Generating health report..."

    local report_file="$DEPLOY_ROOT/health-report-$(date +%Y%m%d-%H%M%S).json"

    cat > "$report_file" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "overall_status": "$HEALTH_STATUS",
  "failed_checks": [],
  "services_checked": [],
  "platform": "$TARGET",
  "environment": "$ENV"
}
}
EOF

    log_info "Health report saved to: $report_file"

    if [[ "$HEALTH_STATUS" == "healthy" ]]; then
        log_success "All health checks passed!"
        return 0
    else
        log_error "Health check failures detected:"
        printf '  - %s\n' "${FAILED_CHECKS[@]}"
        return 1
    fi
}

# Main health check function
main() {
    local TARGET="${DEPLOY_TARGET:-systemd}"
    local ENV="${DEPLOY_ENV:-development}"

    log_info "JustNews Health Check"
    log_info "Platform: $TARGET"
    log_info "Environment: $ENV"

    case $TARGET in
        systemd)
            check_systemd
            ;;
        *)
            log_info "Skipping platform-specific checks for $TARGET"
            ;;
    esac

    check_database
    check_gpu
    check_monitoring

    for service_port in "${SERVICES[@]}"; do
        IFS=':' read -r service port <<< "$service_port"
        check_service "$service" "$port"
    done

    generate_report
}

main "$@"
