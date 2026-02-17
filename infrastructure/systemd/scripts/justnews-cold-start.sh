#!/bin/bash
# Wrapper to run repo cold_start.sh from a stable path
set -euo pipefail
resolve_root() {
  if [[ -n "${JUSTNEWS_ROOT:-}" ]]; then echo "$JUSTNEWS_ROOT"; return 0; fi
  if [[ -r /etc/justnews/global.env ]]; then
    # shellcheck disable=SC1091
    source /etc/justnews/global.env
    [[ -n "${JUSTNEWS_ROOT:-}" ]] && { echo "$JUSTNEWS_ROOT"; return 0; }
    [[ -n "${SERVICE_DIR:-}" ]] && { echo "$SERVICE_DIR"; return 0; }
  fi
  echo "${SERVICE_DIR:-$HOME/JustNews}"
}

REPO_DIR="$(resolve_root)"
SCRIPT="$REPO_DIR/infrastructure/systemd/cold_start.sh"
if [[ -x "$SCRIPT" ]]; then
  exec sudo -n "$SCRIPT"
else
  echo "cold_start.sh not found or not executable at $SCRIPT" >&2
  exit 1
fi
