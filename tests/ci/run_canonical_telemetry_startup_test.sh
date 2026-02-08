#!/usr/bin/env bash
set -euxo pipefail
# CI wrapper: source canonical_system_startup.sh and call start/stop dev telemetry helpers

REPO_ROOT="$(pwd)"
CANONICAL_SCRIPT="$REPO_ROOT/infrastructure/systemd/canonical_system_startup.sh"

if [[ ! -f "$CANONICAL_SCRIPT" ]]; then
  echo "canonical_system_startup.sh not found" >&2
  exit 1
fi

# Ensure docker available
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found, skipping test" >&2
  exit 0
fi

# Set env to opt in
export ENABLE_DEV_TELEMETRY=true

# Source the canonical script (defines functions) but should not invoke main
source "$CANONICAL_SCRIPT"

# Start dev telemetry stack
start_dev_telemetry_stack "$REPO_ROOT"

# Poll demo emitter
for i in {1..30}; do
  if curl -sSf http://localhost:8080/ >/dev/null 2>&1; then
    echo "demo emitter ready"
    break
  fi
  sleep 1
done

# Stop dev telemetry stack
stop_dev_telemetry_stack "$REPO_ROOT"

echo "dev telemetry lifecycle test completed"
