#!/bin/bash
# rollback_native.sh - JustNews native rollback script
# Provides safe rollback capabilities for systemd deployment

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
BACKUP_DIR="${BACKUP_DIR:-/var/backups/justnews}"
ROLLBACK_TIMEOUT="${ROLLBACK_TIMEOUT:-300}"
FORCE_MODE=false

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
        log_error "This script should be run as root (sudo) for full rollback capabilities"
        return 1
    fi
    return 0
}

# List available backups
list_backups() {
    log_info "Available backups in $BACKUP_DIR:"

    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Backup directory not found: $BACKUP_DIR"
        return 1
    fi

    local backups
    backups=$(find "$BACKUP_DIR" -name "*.tar.gz" -type f -printf "%T@ %p\n" 2>/dev/null | sort -nr | head -10)

    if [[ -z "$backups" ]]; then
        log_warning "No backup files found"
        return 1
    fi

    echo "Timestamp              | Backup File"
    echo "-----------------------|--------------------------------"
    echo "$backups" | while read -r timestamp path; do
        printf "%-22s | %s\n" "$(date -d "@${timestamp%.*}" '+%Y-%m-%d %H:%M:%S')" "$(basename "$path")"
    done

    return 0
}

# Validate backup file
validate_backup() {
    local backup_file="$1"

    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file not found: $backup_file"
        return 1
    fi

    # Check if it's a valid tar.gz file
    if ! tar -tzf "$backup_file" >/dev/null 2>&1; then
        log_error "Invalid backup file: $backup_file"
        return 1
    fi

    # Check backup contents
    local expected_files=("agents/" "requirements.txt" "start_services_daemon.sh")
    local missing_files=()

    for file in "${expected_files[@]}"; do
        if ! tar -tzf "$backup_file" | grep -q "^$file"; then
            missing_files+=("$file")
        fi
    done

    if [[ ${#missing_files[@]} -gt 0 ]]; then
        log_warning "Backup may be incomplete. Missing: ${missing_files[*]}"
        if [[ "$FORCE_MODE" != true ]]; then
            log_error "Use --force to proceed with incomplete backup"
            return 1
        fi
    fi

    log_success "Backup file validated: $(basename "$backup_file")"
    return 0
}

# Stop all services
stop_services() {
    log_info "Stopping all JustNews services..."

    local services=(
        "mcp_bus"
        "chief_editor"
        "scout"
        "fact_checker"
        "analyst"
        "synthesizer"
        "critic"
        "memory"
        "reasoning"
        "newsreader"
        "dashboard"
    )

    for service in "${services[@]}"; do
        if systemctl is-active --quiet "justnews@${service}" 2>/dev/null; then
            log_info "Stopping justnews@${service}..."
            systemctl stop "justnews@${service}"
        else
            log_info "Service justnews@${service} is not running"
        fi
    done

    log_success "All services stopped"
}

# Create pre-rollback backup
create_rollback_backup() {
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local backup_file="$BACKUP_DIR/pre_rollback_${timestamp}.tar.gz"

    log_info "Creating pre-rollback backup..."

    mkdir -p "$BACKUP_DIR"

    # Create backup of current state
    if tar -czf "$backup_file" \
        --exclude="*.log" \
        --exclude="*.tmp" \
        --exclude="__pycache__" \
        --exclude="*.pyc" \
        -C "$PROJECT_ROOT" .; then

        log_success "Pre-rollback backup created: $(basename "$backup_file")"
        echo "$backup_file"
        return 0
    else
        log_error "Failed to create pre-rollback backup"
        return 1
    fi
}

# Restore from backup
restore_backup() {
    local backup_file="$1"
    local temp_dir
    temp_dir=$(mktemp -d)

    log_info "Restoring from backup: $(basename "$backup_file")"

    # Extract backup to temporary directory
    if ! tar -xzf "$backup_file" -C "$temp_dir"; then
        log_error "Failed to extract backup"
        rm -rf "$temp_dir"
        return 1
    fi

    # Backup current critical files
    local critical_files=(
        "agents/mcp_bus/main.py"
        "agents/scout/main.py"
        "agents/analyst/main.py"
        "agents/synthesizer/main.py"
        "requirements.txt"
        "start_services_daemon.sh"
    )

    for file in "${critical_files[@]}"; do
        if [[ -f "$PROJECT_ROOT/$file" ]]; then
            cp "$PROJECT_ROOT/$file" "$PROJECT_ROOT/$file.rollback_backup" 2>/dev/null || true
        fi
    done

    # Restore files
    if cp -r "$temp_dir"/* "$PROJECT_ROOT/"; then
        log_success "Files restored from backup"
        rm -rf "$temp_dir"
        return 0
    else
        log_error "Failed to restore files"
        rm -rf "$temp_dir"
        return 1
    fi
}

# Verify rollback
verify_rollback() {
    log_info "Verifying rollback..."

    local critical_files=(
        "agents/mcp_bus/main.py"
        "agents/scout/main.py"
        "agents/analyst/main.py"
        "agents/synthesizer/main.py"
        "requirements.txt"
    )

    local missing_files=()

    for file in "${critical_files[@]}"; do
        if [[ ! -f "$PROJECT_ROOT/$file" ]]; then
            missing_files+=("$file")
        fi
    done

    if [[ ${#missing_files[@]} -gt 0 ]]; then
        log_error "Rollback verification failed. Missing files: ${missing_files[*]}"
        return 1
    fi

    log_success "Rollback verification passed"
    return 0
}

# Restart services
restart_services() {
    log_info "Restarting JustNews services..."

    # Start MCP Bus first
    log_info "Starting MCP Bus..."
    systemctl start justnews@mcp_bus

    # Wait for MCP Bus
    sleep 10

    # Start other services
    local services=(
        "chief_editor"
        "scout"
        "fact_checker"
        "analyst"
        "synthesizer"
        "critic"
        "memory"
        "reasoning"
        "newsreader"
        "dashboard"
    )

    for service in "${services[@]}"; do
        log_info "Starting justnews@${service}..."
        systemctl start "justnews@${service}"
    done

    log_success "Services restarted"
}

# Show usage
show_usage() {
    cat << EOF
JustNews Rollback Script

USAGE:
    $0 [OPTIONS] [BACKUP_FILE]

OPTIONS:
    -l, --list           List available backups
    -f, --force          Force rollback even with validation errors
    -t, --timeout SEC    Rollback timeout in seconds (default: 300)
    -b, --backup-dir DIR Backup directory (default: /var/backups/justnews)
    -h, --help           Show this help message

DESCRIPTION:
    Performs safe rollback of JustNews deployment to a previous backup.
    Automatically stops services, restores files, and restarts services.

EXAMPLES:
    $0 --list                           # List available backups
    $0 /var/backups/justnews/backup_20240901.tar.gz  # Rollback to specific backup
    $0 --force latest                   # Force rollback to latest backup

BACKUP LOCATIONS:
    Default: /var/backups/justnews/
    Format: YYYYMMDD_HHMMSS.tar.gz

EXIT CODES:
    0 - Rollback successful
    1 - Rollback failed
    2 - No backup specified and none found
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -l|--list)
                list_backups
                exit 0
                ;;
            -f|--force)
                FORCE_MODE=true
                shift
                ;;
            -t|--timeout)
                ROLLBACK_TIMEOUT="$2"
                shift 2
                ;;
            -b|--backup-dir)
                BACKUP_DIR="$2"
                shift 2
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                if [[ -z "${BACKUP_FILE:-}" ]]; then
                    BACKUP_FILE="$1"
                else
                    log_error "Multiple backup files specified"
                    show_usage
                    exit 1
                fi
                shift
                ;;
        esac
    done
}

# Find latest backup
find_latest_backup() {
    if [[ ! -d "$BACKUP_DIR" ]]; then
        return 1
    fi

    local latest_backup
    latest_backup=$(find "$BACKUP_DIR" -name "*.tar.gz" -type f -printf "%T@ %p\n" 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)

    if [[ -z "$latest_backup" ]]; then
        return 1
    fi

    echo "$latest_backup"
    return 0
}

# Main function
main() {
    parse_args "$@"

    echo "========================================"
    log_info "JustNews Rollback Script"
    echo "========================================"

    # Check permissions
    if ! check_root; then
        log_warning "Proceeding without root privileges (limited functionality)"
    fi

    # Determine backup file
    if [[ -z "${BACKUP_FILE:-}" ]]; then
        log_info "No backup file specified, looking for latest..."
        BACKUP_FILE=$(find_latest_backup)

        if [[ -z "$BACKUP_FILE" ]]; then
            log_error "No backup files found in $BACKUP_DIR"
            log_info "Use --list to see available backups"
            exit 2
        fi

        log_info "Using latest backup: $(basename "$BACKUP_FILE")"
    fi

    # Validate backup
    if ! validate_backup "$BACKUP_FILE"; then
        exit 1
    fi

    # Create pre-rollback backup
    local pre_backup
    if ! pre_backup=$(create_rollback_backup); then
        if [[ "$FORCE_MODE" != true ]]; then
            log_error "Failed to create pre-rollback backup"
            exit 1
        fi
    else
        log_info "Pre-rollback backup saved: $(basename "$pre_backup")"
    fi

    # Stop services
    stop_services

    # Restore backup
    if ! restore_backup "$BACKUP_FILE"; then
        log_error "Rollback failed during restore"
        exit 1
    fi

    # Verify rollback
    if ! verify_rollback; then
        log_error "Rollback verification failed"
        exit 1
    fi

    # Restart services
    restart_services

    echo
    log_success "🎉 Rollback completed successfully!"
    log_info "Backup restored: $(basename "$BACKUP_FILE")"
    log_info "Pre-rollback backup: $(basename "${pre_backup:-none}")"

    return 0
}

# Run main function
main "$@"
