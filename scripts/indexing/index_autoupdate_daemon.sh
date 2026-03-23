#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=${ROOT_DIR:-/app}
INTERVAL_SECONDS=${INDEX_AUTOUPDATE_INTERVAL_SECONDS:-900}
RUN_DIR=${RUN_DIR:-"$ROOT_DIR/run"}
PID_FILE=${PID_FILE:-"$RUN_DIR/code-index-autoupdate.pid"}
LOG_FILE=${LOG_FILE:-"$RUN_DIR/code-index-autoupdate.log"}

mkdir -p "$RUN_DIR"

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_daemon() {
  if is_running; then
    echo "code-index-autoupdate already running (pid=$(cat "$PID_FILE"))"
    return 0
  fi

  nohup bash -lc '
    set -euo pipefail
    while true; do
      cd "'"$ROOT_DIR"'"
      python3 scripts/indexing/autonomous_index_update.py --root . --index-dir .cache/code_index >> "'"$LOG_FILE"'" 2>&1 || true
      sleep "'"$INTERVAL_SECONDS"'"
    done
  ' >/dev/null 2>&1 &

  local pid=$!
  echo "$pid" > "$PID_FILE"
  echo "started code-index-autoupdate daemon (pid=$pid, interval=${INTERVAL_SECONDS}s)"
}

stop_daemon() {
  if ! is_running; then
    rm -f "$PID_FILE"
    echo "code-index-autoupdate daemon is not running"
    return 0
  fi

  local pid
  pid=$(cat "$PID_FILE")
  kill "$pid" 2>/dev/null || true
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "stopped code-index-autoupdate daemon"
}

status_daemon() {
  if is_running; then
    echo "code-index-autoupdate daemon running (pid=$(cat "$PID_FILE"), interval=${INTERVAL_SECONDS}s, log=$LOG_FILE)"
  else
    echo "code-index-autoupdate daemon not running"
  fi
}

case "${1:-}" in
  start)
    start_daemon
    ;;
  stop)
    stop_daemon
    ;;
  status)
    status_daemon
    ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac
