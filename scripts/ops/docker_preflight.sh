#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${JUSTNEWS_COMPOSE_FILE:-$ROOT_DIR/infrastructure/docker/docker-compose.canonical.yml}"

fail() {
  echo "[ERROR] $1" >&2
  exit 1
}

info() {
  echo "[INFO] $1"
}

info "Running Docker preflight checks..."

command -v docker >/dev/null 2>&1 || fail "docker command not found"

docker compose version >/dev/null 2>&1 || fail "docker compose plugin unavailable"

[[ -f "$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"

if ! docker compose -f "$COMPOSE_FILE" config >/dev/null; then
  fail "compose file validation failed: $COMPOSE_FILE"
fi

info "Docker preflight checks passed."
