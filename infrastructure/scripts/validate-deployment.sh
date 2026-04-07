#!/usr/bin/env bash
# Deployment Validation Script for JustNews (Docker-first canonical runtime)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_ROOT="$PROJECT_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

VALIDATION_PASSED=true
ISSUES_FOUND=()

log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
  ISSUES_FOUND+=("WARNING: $1")
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
  ISSUES_FOUND+=("ERROR: $1")
  VALIDATION_PASSED=false
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

validate_canonical_paths() {
  log_info "Validating canonical Docker-first paths..."

  local required_files=(
    "infrastructure/docker/docker-compose.canonical.yml"
    "scripts/ops/docker_compose.sh"
    "scripts/ops/docker_preflight.sh"
    "start_all_services.sh"
    "stop_all_services.sh"
    "infrastructure/scripts/health-check.sh"
  )

  for rel in "${required_files[@]}"; do
    if [[ -f "$DEPLOY_ROOT/$rel" ]]; then
      log_success "Found: $rel"
    else
      log_error "Missing required file: $rel"
    fi
  done
}

validate_tooling() {
  log_info "Validating required tooling..."

  if ! command_exists docker; then
    log_error "docker command not found"
    return
  fi
  log_success "docker command available"

  if ! docker compose version >/dev/null 2>&1; then
    log_error "docker compose plugin unavailable"
    return
  fi
  log_success "docker compose plugin available"
}

validate_compose_config() {
  log_info "Validating Docker compose configuration..."

  local compose_file="$DEPLOY_ROOT/infrastructure/docker/docker-compose.canonical.yml"
  if [[ ! -f "$compose_file" ]]; then
    log_error "Compose file not found: $compose_file"
    return
  fi

  if command_exists docker && docker compose version >/dev/null 2>&1; then
    if docker compose -f "$compose_file" config >/dev/null 2>&1; then
      log_success "Compose file validation passed"
    else
      log_error "Compose file validation failed"
    fi
  else
    log_warning "Skipping compose config validation because docker compose is unavailable"
  fi

  local required_services=(mariadb chromadb redis mcp-bus)
  local service
  for service in "${required_services[@]}"; do
    if grep -q -E "^  ${service}:" "$compose_file"; then
      log_success "Required compose service present: $service"
    else
      log_error "Required compose service missing: $service"
    fi
  done
}

validate_wrapper_defaults() {
  log_info "Validating start/stop wrapper defaults..."

  local start_wrapper="$DEPLOY_ROOT/start_all_services.sh"
  local stop_wrapper="$DEPLOY_ROOT/stop_all_services.sh"

  if [[ -f "$start_wrapper" ]]; then
    if grep -q 'docker_compose.sh" up' "$start_wrapper"; then
      log_success "start_all_services.sh defaults to docker compose up"
    else
      log_error "start_all_services.sh does not default to docker compose up"
    fi

    if grep -q 'docker_compose.sh" up' "$start_wrapper"; then
      log_success "start_all_services.sh remains pinned to docker compose"
    fi
  fi

  if [[ -f "$stop_wrapper" ]]; then
    if grep -q 'docker_compose.sh" down' "$stop_wrapper"; then
      log_success "stop_all_services.sh defaults to docker compose down"
    else
      log_error "stop_all_services.sh does not default to docker compose down"
    fi

    if grep -q 'docker_compose.sh" down' "$stop_wrapper"; then
      log_success "stop_all_services.sh remains pinned to docker compose"
    fi
  fi
}

validate_legacy_conflicts() {
  log_info "Checking for contradictory legacy runtime messaging in canonical paths..."

  local compose_file="$DEPLOY_ROOT/infrastructure/docker/docker-compose.canonical.yml"
  if [[ -f "$compose_file" ]]; then
    if grep -qi 'docker compose is deprecated' "$compose_file"; then
      log_error "Canonical compose file still claims Docker compose is deprecated"
    else
      log_success "Canonical compose file has no Docker-deprecated messaging"
    fi
  fi
}

generate_report() {
  log_info "Generating validation report..."

  local report_file="$DEPLOY_ROOT/validation-report-$(date +%Y%m%d-%H%M%S).json"

  if command_exists jq; then
    cat > "$report_file" <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "validation_passed": $VALIDATION_PASSED,
  "issues_found": $(printf '%s\n' "${ISSUES_FOUND[@]:-}" | sed '/^$/d' | jq -R . | jq -s .),
  "checks_performed": [
    "canonical_paths",
    "tooling",
    "compose_config",
    "wrapper_defaults",
    "legacy_conflicts"
  ]
}
EOF
  else
    {
      echo "{";
      echo "  \"timestamp\": \"$(date -Iseconds)\",";
      echo "  \"validation_passed\": $VALIDATION_PASSED,";
      echo "  \"issues_found\": [";
      local i=0
      local total=${#ISSUES_FOUND[@]}
      for item in "${ISSUES_FOUND[@]}"; do
        i=$((i + 1))
        if [[ $i -lt $total ]]; then
          printf '    "%s",\n' "${item//\"/\\\"}"
        else
          printf '    "%s"\n' "${item//\"/\\\"}"
        fi
      done
      echo "  ]";
      echo "}";
    } > "$report_file"
  fi

  log_info "Validation report saved to: $report_file"

  if [[ "$VALIDATION_PASSED" == "true" ]]; then
    log_success "All validation checks passed"
    return 0
  fi

  echo -e "${RED}[ERROR]${NC} Validation found ${#ISSUES_FOUND[@]} issue(s)"
  printf '  - %s\n' "${ISSUES_FOUND[@]}"
  return 1
}

main() {
  log_info "JustNews deployment validation (Docker-first)"

  validate_canonical_paths
  validate_tooling
  validate_compose_config
  validate_wrapper_defaults
  validate_legacy_conflicts

  generate_report
}

main "$@"
