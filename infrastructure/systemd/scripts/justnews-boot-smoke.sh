#!/usr/bin/env bash
# Wrapper to run repo boot_smoke_test.sh from a stable path.
# Design: never fail the service (always exit 0); run helper via bash so it
# doesn't depend on execute bit; print a helpful message if missing.
set -uo pipefail

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
SCRIPT="$REPO_DIR/infrastructure/systemd/helpers/boot_smoke_test.sh"

if [[ -r "$SCRIPT" ]]; then
  /usr/bin/env bash "$SCRIPT" || true
  exit 0
else
  echo "[boot-smoke] WARN: boot_smoke_test.sh not found at $SCRIPT (skipping)" >&2
  exit 0
fi
