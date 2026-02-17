#!/usr/bin/env bash
# Follow multiple unit logs with labels
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <service> [service...]" >&2
  echo "Example: $0 analyst fact_checker mcp_bus" >&2
  exit 1
fi
# Build journalctl arguments
pids=()
for svc in "$@"; do
  (
    journalctl -u "justnews@${svc}" -f -n 0 --no-pager | sed -u "s/^/[${svc}] /"
  ) &
  pids+=("$!")
  sleep 0.1
done
trap 'kill ${pids[@]} 2>/dev/null || true' INT TERM EXIT
wait
