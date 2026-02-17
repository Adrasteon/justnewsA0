#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE=$(dirname "$0")/docker-compose.e2e.yml
COMPOSE_CMD=()

if docker compose version >/dev/null 2>&1; then
	COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
	COMPOSE_CMD=(docker-compose)
else
	echo "Docker Compose is required (docker compose preferred)." >&2
	exit 1
fi

echo "Running quick E2E smoke checks (Redis & MariaDB) using Docker Compose: ${COMPOSE_FILE}"

echo "Checking redis..."
"${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" exec -T redis redis-cli ping || { echo "redis ping failed"; exit 2; }

echo "Checking mariadb (test DB and simple query)..."
"${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" exec -T db mysql -u justnews -ptest -e "SELECT 1;" justnews_test || { echo "mariadb simple query failed"; exit 3; }

echo "Smoke checks passed ✅"

exit 0
