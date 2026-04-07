#!/usr/bin/env bash
# Rollback Script for JustNews (Docker-first canonical runtime)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_ROOT="$PROJECT_ROOT"
COMPOSE_WRAPPER="$PROJECT_ROOT/scripts/ops/docker_compose.sh"
COMPOSE_FILE="${JUSTNEWS_COMPOSE_FILE:-$PROJECT_ROOT/infrastructure/docker/docker-compose.canonical.yml}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

show_help() {
  cat <<EOF
JustNews Rollback Script (Docker-first)

USAGE:
  $0 [OPTIONS]

OPTIONS:
  -e, --env ENV              Environment label for logs (development/staging/production)
  -s, --service SERVICE      Roll back only one compose service (default: all services)
  -f, --force                Skip confirmation prompt
  --skip-health-check        Skip post-rollback health verification
  -h, --help                 Show this help

NOTES:
  - Canonical rollback path is Docker Compose.
  - This script performs an operational rollback by restarting services via compose.
  - Version pin/image-tag rollback should be done by updating compose/image refs then rerunning this script.

EXAMPLES:
  # Roll back full stack by restarting containers
  $0 --env production

  # Roll back only mcp-bus service
  $0 --service mcp-bus

  # Non-interactive rollback
  $0 --force
EOF
}

parse_args() {
  ENV="${DEPLOY_ENV:-development}"
  SERVICE=""
  FORCE="${FORCE_ROLLBACK:-0}"
  SKIP_HEALTH_CHECK="0"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -e|--env)
        ENV="$2"
        shift 2
        ;;
      -s|--service)
        SERVICE="$2"
        shift 2
        ;;
      -f|--force)
        FORCE=1
        shift
        ;;
      --skip-health-check)
        SKIP_HEALTH_CHECK=1
        shift
        ;;
      -h|--help)
        show_help
        exit 0
        ;;
      *)
        log_error "Unknown option: $1"
        show_help
        exit 1
        ;;
    esac
  done
}

confirm_rollback() {
  if [[ "$FORCE" == "1" ]]; then
    return 0
  fi

  local target_msg="docker-compose stack"
  if [[ -n "$SERVICE" ]]; then
    target_msg="docker-compose service '$SERVICE'"
  fi

  echo "This will restart ${target_msg} using compose file: $COMPOSE_FILE"
  read -r -p "Proceed with rollback? (y/N): " reply
  if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    log_info "Rollback cancelled"
    exit 0
  fi
}

ensure_requirements() {
  [[ -x "$COMPOSE_WRAPPER" ]] || {
    log_error "Compose wrapper not found/executable: $COMPOSE_WRAPPER"
    exit 1
  }

  [[ -f "$COMPOSE_FILE" ]] || {
    log_error "Compose file not found: $COMPOSE_FILE"
    exit 1
  }
}

create_backup() {
  log_info "Creating pre-rollback backup snapshot..."

  local backup_dir="$DEPLOY_ROOT/backups/$(date +%Y%m%d-%H%M%S)-rollback"
  mkdir -p "$backup_dir"

  export JUSTNEWS_COMPOSE_FILE="$COMPOSE_FILE"
  if ! "$COMPOSE_WRAPPER" status > "$backup_dir/compose-ps.txt" 2>&1; then
    log_warning "Could not capture compose status before rollback"
  fi

  if command -v docker >/dev/null 2>&1; then
    if ! docker compose -f "$COMPOSE_FILE" images > "$backup_dir/compose-images.txt" 2>&1; then
      log_warning "Could not capture compose image inventory"
    fi
  fi

  log_success "Backup snapshot created: $backup_dir"
}

rollback_compose() {
  export JUSTNEWS_COMPOSE_FILE="$COMPOSE_FILE"

  if [[ -n "$SERVICE" ]]; then
    log_info "Rolling back service: $SERVICE"
    "$COMPOSE_WRAPPER" up --no-deps --force-recreate -d "$SERVICE"
  else
    log_info "Rolling back full stack"
    "$COMPOSE_WRAPPER" down
    "$COMPOSE_WRAPPER" up
  fi

  log_success "Compose rollback actions completed"
}

verify_rollback() {
  if [[ "$SKIP_HEALTH_CHECK" == "1" ]]; then
    log_warning "Skipping health verification by request"
    return 0
  fi

  local health_script="$DEPLOY_ROOT/infrastructure/scripts/health-check.sh"
  if [[ -f "$health_script" ]]; then
    log_info "Running post-rollback health check..."
    if DEPLOY_TARGET=docker bash "$health_script"; then
      log_success "Rollback verification passed"
      return 0
    fi

    log_error "Rollback verification failed"
    return 1
  fi

  log_warning "Health check script not found, skipping verification"
  return 0
}

log_rollback_event() {
  local log_file="$DEPLOY_ROOT/logs/rollback-$(date +%Y%m%d).log"
  mkdir -p "$DEPLOY_ROOT/logs"

  cat >> "$log_file" <<EOF
$(date -Iseconds) - Rollback executed
Target: docker
Environment: $ENV
Service: ${SERVICE:-all}
ComposeFile: $COMPOSE_FILE
Status: completed
EOF

  log_info "Rollback logged to: $log_file"
}

main() {
  parse_args "$@"
  ensure_requirements

  log_info "JustNews rollback (Docker-first)"
  log_info "Environment: $ENV"
  if [[ -n "$SERVICE" ]]; then
    log_info "Service: $SERVICE"
  fi

  confirm_rollback
  create_backup
  rollback_compose
  verify_rollback
  log_rollback_event

  log_success "Rollback operation completed successfully"
}

main "$@"
