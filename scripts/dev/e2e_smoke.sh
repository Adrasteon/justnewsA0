#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE=$(dirname "$0")/docker-compose.e2e.yml

echo "Running quick E2E smoke checks (Redis & MariaDB) using docker-compose: ${COMPOSE_FILE}"

echo "Checking redis..."
docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping || { echo "redis ping failed"; exit 2; }

echo "Checking mariadb (test DB and simple query)..."
docker-compose -f "$COMPOSE_FILE" exec -T db mysql -u justnews -ptest -e "SELECT 1;" justnews_test || { echo "mariadb simple query failed"; exit 3; }

echo "Smoke checks passed ✅"

exit 0
