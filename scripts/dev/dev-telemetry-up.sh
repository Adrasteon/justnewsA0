#!/usr/bin/env bash
set -euo pipefail

# Small helper to bring up the local dev telemetry stack (Loki + Tempo + OTel node)
COMPOSE_FILE="infrastructure/monitoring/dev-docker-compose.yaml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Missing compose file: $COMPOSE_FILE"
  exit 1
fi

echo "Starting dev telemetry stack (Loki, Tempo, OTel node)..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Telemetry stack started. Endpoints:"
echo " - Loki: http://localhost:3100"
echo " - Tempo (jaeger/http): http://localhost:9411"
echo " - OTel node collector OTLP gRPC: localhost:4317"

echo "Run 'docker compose -f $COMPOSE_FILE logs -f' to tail logs, or 'docker compose -f $COMPOSE_FILE down' to stop."
