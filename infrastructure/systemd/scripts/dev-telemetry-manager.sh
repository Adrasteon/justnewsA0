#!/usr/bin/env bash
set -euo pipefail

# Small wrapper to manage the repo dev telemetry stack in a systemd-friendly way.
# Delegates logic to the canonical startup helper functions so we keep behaviour
# consistent with canonical_system_startup.sh (port checks, invoker selection).

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/infrastructure/systemd/canonical_system_startup.sh"

if [[ ! -f "$SCRIPT" ]]; then
  echo "Missing canonical startup helper: $SCRIPT" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 up|down" >&2
  exit 2
fi

cmd="$1"

# Source the canonical file so we can call start_dev_telemetry_stack / stop_dev_telemetry_stack
# (these functions are idempotent and mirror the startup flow used elsewhere).
# shellcheck source=../canonical_system_startup.sh
. "$SCRIPT"

case "$cmd" in
  up)
    ENABLE_DEV_TELEMETRY=true start_dev_telemetry_stack "$REPO_ROOT"
    ;;
  down)
    ENABLE_DEV_TELEMETRY=true stop_dev_telemetry_stack "$REPO_ROOT"
    ;;
  *)
    echo "Unknown command: $cmd; expected up or down" >&2
    exit 2
    ;;
esac
