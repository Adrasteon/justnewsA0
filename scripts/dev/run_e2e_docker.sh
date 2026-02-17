#!/usr/bin/env bash
set -euo pipefail

# Lightweight helper: Docker-based E2E proof-of-concept for JustNews
# Starts MariaDB + Redis via Docker Compose and runs the repository's E2E tests

COMPOSE_FILE=$(dirname "$0")/docker-compose.e2e.yml
REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
COMPOSE_CMD=()

function init_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    return 0
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    return 0
  fi

  echo "Docker Compose is required. Install Docker Compose plugin (preferred) or docker-compose." >&2
  exit 1
}

function require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required. Install it and try again." >&2
    exit 1
  fi
}

require_docker
init_compose_cmd

echo "Bringing up mariadb + redis (Docker Compose)..."
# If a pre-seeded image is not present locally, build it (faster CI/PoC path)
if ! docker image inspect justnews/mariadb-preseed:local >/dev/null 2>&1; then
  echo "Preseeded Mariadb image not found locally — building one (justnews/mariadb-preseed:local)..."
  docker build -t justnews/mariadb-preseed:local -f "$REPO_ROOT/scripts/dev/db-mariadb/Dockerfile" "$REPO_ROOT/scripts/dev"
fi

"${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" up -d --remove-orphans

echo "Waiting for services to become healthy (this may take a little while)"
sleep 3

echo "Polling health checks..."
"${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" ps

echo "Once both services show healthy status, run pytest (local environment must have test deps installed).
Example env vars we use for this PoC (local host-port mapping):
  MARIADB_HOST=127.0.0.1
  MARIADB_PORT=13306
  MARIADB_DB=justnews_test
  MARIADB_USER=justnews
  MARIADB_PASSWORD=test
  REDIS_URL=redis://127.0.0.1:16379

To run tests now, ensure your Python environment has the repo's requirements installed and run:

  MARIADB_HOST=127.0.0.1 MARIADB_PORT=13306 MARIADB_DB=justnews_test MARIADB_USER=justnews \
    MARIADB_PASSWORD=test REDIS_URL=redis://127.0.0.1:16379 PYTEST_RUNNING=1 E2E_REAL=1 \
    pytest -q tests/e2e -q -s"

echo "To tear down: ${COMPOSE_CMD[*]} -f $COMPOSE_FILE down"

exit 0
