#!/usr/bin/env bash
set -euo pipefail

# ensure_global_python_bin.sh
# Ensure /etc/justnews/global.env contains a valid PYTHON_BIN setting.
# - If the file is missing, it will create it with a safe default.
# - If PYTHON_BIN is absent, this script will add a canonical value derived
#   from the requested CONDA_ENV (default: ${CANONICAL_ENV:-justnews-py312-phase1}).
# - Does not overwrite an existing PYTHON_BIN unless --force is passed.

GLOBAL_ENV="/etc/justnews/global.env"
DEFAULT_CONDA_ENV="${CONDA_ENV:-${CANONICAL_ENV:-justnews-py312-phase1}}"
DEFAULT_PY_BIN="$HOME/miniconda3/envs/${DEFAULT_CONDA_ENV}/bin/python"

usage() {
  cat <<EOF
Usage: $0 [--force] [--env-file <path>] [--conda-env <env>]

Ensure the global environment file contains PYTHON_BIN set to a valid interpreter.
--force       Overwrite an existing PYTHON_BIN entry if present
--env-file    Path to global.env (default: /etc/justnews/global.env)
--conda-env   Conda env name to derive default PYTHON_BIN from
EOF
}

FORCE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=true; shift ;;
    --env-file) GLOBAL_ENV="$2"; shift 2 ;;
    --conda-env) DEFAULT_CONDA_ENV="$2"; DEFAULT_PY_BIN="$HOME/miniconda3/envs/${DEFAULT_CONDA_ENV}/bin/python"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

ensure_file_exists() {
  if [[ ! -f "$GLOBAL_ENV" ]]; then
    mkdir -p "$(dirname "$GLOBAL_ENV")"
    cat > "$GLOBAL_ENV" <<EOF
# Auto-created global.env by ensure_global_python_bin.sh
SERVICE_DIR=${SERVICE_DIR:-$HOME/JustNews}
PYTHON_BIN=${DEFAULT_PY_BIN}
EOF
    chmod 644 "$GLOBAL_ENV" || true
    echo "Created $GLOBAL_ENV with PYTHON_BIN=$DEFAULT_PY_BIN"
    return 0
  fi
}

read_current_setting() {
  # shellcheck disable=SC1090
  . "$GLOBAL_ENV"
  echo "${PYTHON_BIN:-}"
}

set_python_bin() {
  local current
  current=$(read_current_setting || true)
  if [[ -n "$current" && "$FORCE" != true ]]; then
    echo "PYTHON_BIN already set to: $current (use --force to overwrite)"
    return 0
  fi

  if [[ -n "$current" && "$FORCE" == true ]]; then
    # overwrite safely with backup
    cp -a "$GLOBAL_ENV" "$GLOBAL_ENV.bak_$(date +%Y%m%d_%H%M%S)" || true
    echo "Overwriting PYTHON_BIN in $GLOBAL_ENV (backup created)"
    # Use sed to replace existing line, fallback to append if not found
    if grep -q '^PYTHON_BIN=' "$GLOBAL_ENV"; then
      sed -i "s|^PYTHON_BIN=.*|PYTHON_BIN=${DEFAULT_PY_BIN}|" "$GLOBAL_ENV"
    else
      echo "PYTHON_BIN=${DEFAULT_PY_BIN}" >> "$GLOBAL_ENV"
    fi
    echo "PYTHON_BIN set to ${DEFAULT_PY_BIN}"
    return 0
  fi

  # If not present, append
  echo "PYTHON_BIN=${DEFAULT_PY_BIN}" >> "$GLOBAL_ENV"
  echo "PYTHON_BIN written to $GLOBAL_ENV -> ${DEFAULT_PY_BIN}"
}

main() {
  ensure_file_exists
  set_python_bin
  # Validate resulting path
  # shellcheck disable=SC1090
  . "$GLOBAL_ENV"
  if [[ -x "${PYTHON_BIN:-}" ]]; then
    echo "PYTHON_BIN validated: ${PYTHON_BIN}"
    return 0
  else
    echo "Warning: PYTHON_BIN '${PYTHON_BIN:-}' is not executable on this host" >&2
    echo "If the path is incorrect, update $GLOBAL_ENV to point to the correct interpreter." >&2
    return 1
  fi
}

main
