#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPOSE_FILE="${REPO_ROOT}/scripts/dev/docker-compose.e2e.yml"

echo "Bringing up e2e services (MariaDB, Redis, Chroma)..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Waiting for services to be ready (MariaDB/Redis/Chroma)"
ATTEMPTS=60
i=0
until docker compose -f "$COMPOSE_FILE" ps | grep -E 'db|redis|chroma' >/dev/null; do
  i=$((i+1))
  if [ "$i" -ge "$ATTEMPTS" ]; then
    echo "Timed out waiting for services to come up" >&2
    docker compose -f "$COMPOSE_FILE" ps
    exit 1
  fi
  sleep 1
done

echo "Exporting environment flags for 'full' local integration runs."
# These enable the gated tests in the test-suite
export RUN_REAL_E2E=1
export ENABLE_DB_INTEGRATION_TESTS=1
export ENABLE_CHROMADB_LIVE_TESTS=1
export RUN_PROVIDER_TESTS=1

echo "Note: provider tests may still require credentials (e.g. OPENAI_API_KEY)."
echo "If you need to run provider tests, export OPENAI_API_KEY and any other keys before running this script."

echo "Now running pytest via scripts/run_with_env.sh — pass additional pytest args if needed."
ARGS=("${@:-}" )
if [ ${#ARGS[@]} -eq 0 ]; then
  # Run the full test suite by default; use -q for concise output
  ARGS=("-q")
fi

exec "$REPO_ROOT/scripts/run_with_env.sh" pytest "${ARGS[@]}"
