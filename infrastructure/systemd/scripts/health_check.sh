#!/usr/bin/env bash
# PATH wrapper to call the repo's health_check.sh regardless of CWD
set -euo pipefail

resolve_root() {
  if [[ -n "${JUSTNEWS_ROOT:-}" ]]; then
    echo "$JUSTNEWS_ROOT"; return 0
  fi
  if [[ -r /etc/justnews/global.env ]]; then
    # shellcheck disable=SC1091
    source /etc/justnews/global.env
    if [[ -n "${JUSTNEWS_ROOT:-}" ]]; then echo "$JUSTNEWS_ROOT"; return 0; fi
    if [[ -n "${SERVICE_DIR:-}" ]]; then echo "$SERVICE_DIR"; return 0; fi
  fi
  echo "${SERVICE_DIR:-$HOME/JustNews}"
}

ROOT="$(resolve_root)"
SCRIPT="$ROOT/infrastructure/systemd/health_check.sh"
if [[ -x "$SCRIPT" ]]; then
  exec "$SCRIPT" "$@"
else
  echo "health_check.sh not found or not executable at $SCRIPT" >&2
  exit 1
fi
