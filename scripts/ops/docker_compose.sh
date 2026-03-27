#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE_DEFAULT="$ROOT_DIR/infrastructure/docker/docker-compose.canonical.yml"
COMPOSE_FILE="${JUSTNEWS_COMPOSE_FILE:-$COMPOSE_FILE_DEFAULT}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker command not found" >&2
  exit 127
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin unavailable" >&2
  exit 127
fi

usage() {
  cat <<EOF
Usage: $(basename "$0") <up|down|status|logs|ps> [extra docker compose args]

Environment:
  JUSTNEWS_COMPOSE_FILE   Override compose file path
EOF
}

cmd="${1:-}"
if [[ -z "$cmd" ]]; then
  usage
  exit 2
fi
shift || true

case "$cmd" in
  up)
    exec docker compose -f "$COMPOSE_FILE" up -d "$@"
    ;;
  down)
    exec docker compose -f "$COMPOSE_FILE" down "$@"
    ;;
  status|ps)
    exec docker compose -f "$COMPOSE_FILE" ps "$@"
    ;;
  logs)
    exec docker compose -f "$COMPOSE_FILE" logs -f "$@"
    ;;
  *)
    usage
    exit 2
    ;;
esac
