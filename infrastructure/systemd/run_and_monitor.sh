#!/bin/bash
set -euo pipefail

# run_and_monitor.sh — wrapper to run canonical_system_startup.sh with
# live journal and coredump capture. Intended to be executed as root (sudo).
# Usage: sudo ./run_and_monitor.sh [--dry-run] [other args passed to script]

CANONICAL="${SERVICE_DIR:-$HOME/JustNews}/infrastructure/systemd/canonical_system_startup.sh"
LOGDIR="/var/log/justnews"
mkdir -p "$LOGDIR"
TS=$(date +%Y%m%d_%H%M%S)
RUNLOG="$LOGDIR/canonical_run_$TS.log"
JOURNALLOG="$LOGDIR/journal_$TS.log"
COREDUMPLOG="$LOGDIR/coredumps_$TS.log"

echo "[INFO] Starting run_and_monitor.sh"
echo "[INFO] Run log: $RUNLOG"
echo "[INFO] Journal log: $JOURNALLOG"
echo "[INFO] Coredump log: $COREDUMPLOG"

if [[ ! -x "$CANONICAL" ]]; then
  echo "[ERROR] Canonical script not found or not executable: $CANONICAL" >&2
  exit 1
fi

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] This script should be run as root (sudo)." >&2
  exit 1
fi

# Start journal capture in background
journalctl -f -o short-iso --no-pager > "$JOURNALLOG" 2>&1 &
JPID=$!

# Start coredump polling in background (periodically write current list)
( while true; do coredumpctl list --no-pager > "$COREDUMPLOG" 2>&1 || true; sleep 5; done ) &
CPID=$!

# Run canonical script with debug tracing and tee output to run log
echo "[INFO] Executing: bash -x $CANONICAL $*"
bash -x "$CANONICAL" "$@" 2>&1 | tee "$RUNLOG"
EXIT=$?

# Allow background captures to flush
sleep 1

echo "[INFO] Stopping background capture processes"
kill $JPID $CPID 2>/dev/null || true
wait $JPID 2>/dev/null || true
wait $CPID 2>/dev/null || true

echo "[INFO] Execution finished (exit code: $EXIT)"
echo "[INFO] Logs are available:" 
echo "  run: $RUNLOG"
echo "  journal: $JOURNALLOG"
echo "  coredumps: $COREDUMPLOG"

exit $EXIT
