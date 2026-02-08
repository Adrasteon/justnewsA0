#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${SERVICE_DIR:-$(pwd)}"
COMPOSE="$BASE_DIR/infrastructure/monitoring/dev-docker-compose.yaml"

if [[ ! -f "$COMPOSE" ]]; then
  echo "dev-docker-compose not found at $COMPOSE" >&2
  exit 2
fi

if command -v docker >/dev/null 2>&1; then
  echo "Checking docker containers for justnews-"
  docker ps --filter "name=justnews-" --format "{{.Names}}: {{.Status}}"
else
  echo "docker not available on host" >&2
  exit 1
fi

echo "Checking demo emitter probe..."
if curl -sSf http://localhost:8080/ >/dev/null 2>&1; then
  echo "Demo emitter responding: OK"
else
  echo "Demo emitter probe failed" >&2
  exit 3
fi

echo "Dev telemetry status looks healthy"
