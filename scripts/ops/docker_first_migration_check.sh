#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_CANONICAL="$ROOT_DIR/infrastructure/docker/docker-compose.canonical.yml"
COMPOSE_POINTER="$ROOT_DIR/infrastructure/docker/docker-compose.yml"
DOCKER_WRAPPER="$ROOT_DIR/scripts/ops/docker_compose.sh"
PREFLIGHT="$ROOT_DIR/scripts/ops/docker_preflight.sh"
START_WRAPPER="$ROOT_DIR/start_all_services.sh"
STOP_WRAPPER="$ROOT_DIR/stop_all_services.sh"

ok=0
warn=0
fail=0

pass() { echo "[PASS] $1"; ok=$((ok+1)); }
warning() { echo "[WARN] $1"; warn=$((warn+1)); }
error() { echo "[FAIL] $1"; fail=$((fail+1)); }

check_file() {
  local path="$1"
  local label="$2"
  if [[ -f "$path" ]]; then
    pass "$label exists ($path)"
  else
    error "$label missing ($path)"
  fi
}

check_exec() {
  local path="$1"
  local label="$2"
  if [[ -x "$path" ]]; then
    pass "$label executable ($path)"
  elif [[ -f "$path" ]]; then
    warning "$label exists but is not executable ($path)"
  else
    error "$label missing ($path)"
  fi
}

check_contains() {
  local path="$1"
  local needle="$2"
  local label="$3"
  if grep -q "$needle" "$path"; then
    pass "$label"
  else
    error "$label (needle '$needle' not found in $path)"
  fi
}

echo "Docker-First Migration Compliance Check"
echo "====================================="

check_file "$COMPOSE_CANONICAL" "Canonical compose file"
check_file "$COMPOSE_POINTER" "Legacy compose pointer file"
check_exec "$DOCKER_WRAPPER" "Docker compose wrapper"
check_exec "$PREFLIGHT" "Docker preflight script"
check_exec "$START_WRAPPER" "start_all_services wrapper"
check_exec "$STOP_WRAPPER" "stop_all_services wrapper"

if [[ -f "$COMPOSE_POINTER" ]]; then
  check_contains "$COMPOSE_POINTER" "docker-compose.canonical.yml" "Legacy compose path points to canonical compose file"
fi

if [[ -f "$START_WRAPPER" ]]; then
  check_contains "$START_WRAPPER" "docker_compose.sh\" up" "start_all_services defaults to Docker up"
  check_contains "$START_WRAPPER" "JUSTNEWS_ENABLE_LEGACY_START_STOP" "start_all_services supports legacy transition toggle"
fi

if [[ -f "$STOP_WRAPPER" ]]; then
  check_contains "$STOP_WRAPPER" "docker_compose.sh\" down" "stop_all_services defaults to Docker down"
  check_contains "$STOP_WRAPPER" "JUSTNEWS_ENABLE_LEGACY_START_STOP" "stop_all_services supports legacy transition toggle"
fi

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    if docker compose -f "$COMPOSE_CANONICAL" config >/dev/null 2>&1; then
      pass "Docker compose config validation passed"
    else
      warning "Docker compose plugin present but canonical compose validation failed"
    fi
  else
    warning "docker command found but compose plugin unavailable"
  fi
else
  warning "docker command not found on host"
fi

echo
echo "Summary: PASS=$ok WARN=$warn FAIL=$fail"

if [[ $fail -gt 0 ]]; then
  exit 1
fi

exit 0
