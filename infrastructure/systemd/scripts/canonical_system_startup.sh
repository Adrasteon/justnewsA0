#!/usr/bin/env bash
set -euo pipefail

resolve_root() {
  if [[ -n "${JUSTNEWS_ROOT:-}" ]]; then
    echo "$JUSTNEWS_ROOT"; return 0
  fi
  if [[ -r /etc/justnews/global.env ]]; then
    # shellcheck disable=SC1091
    source /etc/justnews/global.env
    if [[ -n "${JUSTNEWS_ROOT:-}" ]]; then
      echo "$JUSTNEWS_ROOT"; return 0
    fi
    if [[ -n "${SERVICE_DIR:-}" ]]; then
      echo "$SERVICE_DIR"; return 0
    fi
  fi
  echo "${SERVICE_DIR:-$HOME/JustNews}"
}

ROOT="$(resolve_root)"
SCRIPT="$ROOT/infrastructure/systemd/canonical_system_startup.sh"
if [[ ! -x "$SCRIPT" ]]; then
  echo "canonical_system_startup.sh not found or not executable at $SCRIPT" >&2
  exit 1
fi
# Ensure PYTHONPATH and PYTHON_BIN are exported so downstream services and
# scripts can correctly run using the project's conda environment. If
# `/etc/justnews/global.env` or project `global.env` has been sourced, those
# values will be used; otherwise prefer the canonical project env (CANONICAL_ENV, default: justnews-py312)
export PYTHON_BIN="${PYTHON_BIN:-$HOME/miniconda3/envs/${CANONICAL_ENV:-justnews-py312-phase1}/bin/python}"
export PYTHONPATH="${PYTHONPATH:-$ROOT}"
# PYTHON_BIN default derived from CANONICAL_ENV when present

exec "$SCRIPT" "$@"
