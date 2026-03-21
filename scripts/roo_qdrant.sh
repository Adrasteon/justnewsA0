#!/usr/bin/env bash

set -euo pipefail

CONTAINER_NAME="${QDRANT_CONTAINER_NAME:-roo-qdrant}"
IMAGE="${QDRANT_IMAGE:-qdrant/qdrant:latest}"
PORT="${QDRANT_PORT:-6333}"
HEALTH_URL="${QDRANT_HEALTH_URL:-http://host.docker.internal:${PORT}/collections}"

usage() {
  cat <<'EOF'
Usage: scripts/roo_qdrant.sh <command>

Commands:
  start    Start Qdrant container (or no-op if already running)
  stop     Stop and remove Qdrant container (no-op if missing)
  restart  Restart Qdrant container
  status   Show container status and endpoint health
  health   Probe endpoint health only
  logs     Show recent container logs

Environment overrides:
  QDRANT_CONTAINER_NAME   Container name (default: roo-qdrant)
  QDRANT_IMAGE            Image name (default: qdrant/qdrant:latest)
  QDRANT_PORT             Host/container port (default: 6333)
  QDRANT_HEALTH_URL       Health URL (default: http://host.docker.internal:<port>/collections)
EOF
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is not installed or not on PATH"
    exit 1
  fi
}

exists() {
  docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"
}

running() {
  docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"
}

start_qdrant() {
  require_docker

  if running; then
    echo "${CONTAINER_NAME} is already running"
    return
  fi

  if exists; then
    echo "Starting existing container ${CONTAINER_NAME}"
    docker start "${CONTAINER_NAME}" >/dev/null
  else
    echo "Creating and starting ${CONTAINER_NAME} (${IMAGE}) on port ${PORT}"
    docker run -d --name "${CONTAINER_NAME}" -p "${PORT}:${PORT}" "${IMAGE}" >/dev/null
  fi

  health_qdrant || true
}

stop_qdrant() {
  require_docker

  if exists; then
    echo "Stopping/removing ${CONTAINER_NAME}"
    docker rm -f "${CONTAINER_NAME}" >/dev/null
  else
    echo "${CONTAINER_NAME} does not exist"
  fi
}

health_qdrant() {
  echo "Probing ${HEALTH_URL}"
  if curl -fsS --connect-timeout 2 --max-time 8 "${HEALTH_URL}" >/dev/null; then
    echo "Qdrant endpoint is healthy"
    return 0
  fi
  echo "Qdrant endpoint is NOT reachable"
  return 1
}

status_qdrant() {
  require_docker

  if running; then
    echo "${CONTAINER_NAME}: running"
  elif exists; then
    echo "${CONTAINER_NAME}: stopped"
  else
    echo "${CONTAINER_NAME}: missing"
  fi

  docker ps -a --filter "name=^${CONTAINER_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  health_qdrant || true
}

logs_qdrant() {
  require_docker

  if exists; then
    docker logs --tail 80 "${CONTAINER_NAME}"
  else
    echo "${CONTAINER_NAME} does not exist"
    exit 1
  fi
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    start)
      start_qdrant
      ;;
    stop)
      stop_qdrant
      ;;
    restart)
      stop_qdrant
      start_qdrant
      ;;
    status)
      status_qdrant
      ;;
    health)
      health_qdrant
      ;;
    logs)
      logs_qdrant
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      echo "Unknown command: ${cmd}"
      usage
      exit 2
      ;;
  esac
}

main "$@"
