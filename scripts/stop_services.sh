#!/usr/bin/env bash
# scripts/stop_services.sh — stop development agents launched via start_services_daemon.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { printf "%s [%s] %s\n" "$(timestamp)" "$1" "$2"; }
info() { log INFO "$*"; }
warn() { log WARN "$*"; }

if [ -f "$SCRIPT_DIR/infrastructure/agents_manifest.sh" ]; then
  # shellcheck disable=SC1090
  . "$SCRIPT_DIR/infrastructure/agents_manifest.sh"
else
  info "No manifest found — nothing to stop"
  exit 0
fi

for entry in "${AGENTS_MANIFEST[@]}"; do
  IFS='|' read -r name module port <<< "$entry"
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    info "Attempting graceful shutdown of $name on port $port"
    if command -v curl >/dev/null 2>&1; then
      code=$(curl -s -o /dev/null -w "%{http_code}" -X POST --max-time 5 "http://127.0.0.1:$port/shutdown" || true)
      if [ "$code" = "200" ] || [ "$code" = "202" ] || [ "$code" = "204" ]; then
        info "Shutdown accepted (code $code), waiting up to 15s for port to close"
        deadline=$(( $(date +%s) + 15 ))
        while ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN && [ $(date +%s) -le $deadline ]; do
          sleep 1
        done
        if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
          warn "Port $port still listening after graceful request — forcing kill"
        else
          info "Port $port freed"
          continue
        fi
      else
        warn "Shutdown endpoint did not respond properly (code=$code) — will attempt to kill process"
      fi
    else
      warn "curl not available; will attempt to kill process listening on port $port"
    fi
    # Attempt to kill owner PID(s)
    if command -v lsof >/dev/null 2>&1; then
      pids=$(lsof -ti tcp:"$port" || true)
    else
      pids=$(ss -ltnp 2>/dev/null | grep -E ":$port\b" | sed -n 's/.*pid=\([0-9]*\),.*/\1/p' | tr '\n' ' ')
    fi
    if [ -n "${pids:-}" ]; then
      for pid in $pids; do
        info "Killing pid $pid (port $port)"
        kill -TERM "$pid" 2>/dev/null || true
      done
      sleep 2
      for pid in $pids; do
        if ps -p "$pid" >/dev/null 2>&1; then
          info "PID $pid still alive; SIGKILL"
          kill -9 "$pid" 2>/dev/null || true
        fi
      done
    else
      info "No owning PIDs discovered for port $port"
    fi
  else
    info "$name (port $port) not listening — nothing to do"
  fi
done

info "Stop pass completed"
