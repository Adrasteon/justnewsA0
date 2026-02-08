#!/usr/bin/env bash
set -euo pipefail

# Stop any locally-running JustNews agent processes started with `python -m agents.*`
# This script attempts a graceful shutdown (SIGTERM) then force kills remaining (SIGKILL).

PIDS=$(pgrep -af "python -m agents\." | awk '{print $1}' || true)
if [ -z "$PIDS" ]; then
  echo "No local agents found."
  exit 0
fi

echo "Stopping local agents: $PIDS"
for p in $PIDS; do
  echo "Terminating PID $p" && kill -TERM "$p" || true
done

# wait up to 10s for processes to exit
for i in $(seq 1 10); do
  sleep 1
  REMAINING="$(pgrep -af "python -m agents\." | awk '{print $1}' || true)"
  if [ -z "$REMAINING" ]; then
    echo "All agents stopped gracefully."
    exit 0
  fi
done

echo "Some agents still running after SIGTERM — force killing:"
pgrep -af "python -m agents\." || true
pkill -9 -f "python -m agents\." || true

echo "Done. Remaining agent processes (if any):"
pgrep -af "python -m agents\." || echo "none"
