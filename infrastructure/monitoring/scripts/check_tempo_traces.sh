#!/usr/bin/env bash
set -euo pipefail

# Usage: check_tempo_traces.sh <tempo_base_url> <service_name> [timeout_secs] [sleep_secs]
# Example: check_tempo_traces.sh http://localhost:24268 justnews-demo-emitter 60 5

BASE_URL=${1:-"http://localhost:${TEMPO_HTTP_PORT:-24268}"}
SERVICE=${2:-"justnews-demo-emitter"}
TIMEOUT_SECS=${3:-60}
SLEEP_SECS=${4:-5}

echo "Checking Tempo at ${BASE_URL} for traces from service='${SERVICE}' (timeout ${TIMEOUT_SECS}s)"

attempts=$(( (TIMEOUT_SECS + SLEEP_SECS - 1) / SLEEP_SECS ))

for i in $(seq 1 $attempts); do
  echo "Attempt $i of $attempts"
  if curl -sSf "${BASE_URL}/api/traces?service=${SERVICE}&limit=1" -o /tmp/tempo_response.json; then
    body=$(cat /tmp/tempo_response.json)
    # If body contains "data":[] then there are no traces. Accept any non-empty data array.
    if echo "$body" | grep -q '"data"\s*:\s*\[\s*\]'; then
      echo "No traces yet in Tempo for service=${SERVICE}"
    else
      echo "Found traces in Tempo for service=${SERVICE}"
      rm -f /tmp/tempo_response.json
      exit 0
    fi
  else
    echo "Tempo query not yet available at ${BASE_URL} (curl failed)"
  fi
  sleep "$SLEEP_SECS"
done

echo "Timed out waiting for Tempo to contain traces for service=${SERVICE} at ${BASE_URL}"
exit 1
