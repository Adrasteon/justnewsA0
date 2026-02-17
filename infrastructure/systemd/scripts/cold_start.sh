#!/usr/bin/env bash
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
ROOT="$(resolve_root)"
SCRIPT="$ROOT/infrastructure/systemd/cold_start.sh"
[[ -x "$SCRIPT" ]] || { echo "cold_start.sh missing at $SCRIPT" >&2; exit 1; }
exec "$SCRIPT" "$@"
