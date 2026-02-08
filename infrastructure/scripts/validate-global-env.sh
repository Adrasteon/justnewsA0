#!/usr/bin/env bash
set -euo pipefail

# validate-global-env.sh — CI / operator validation helper
# This script validates that a PYTHON_BIN variable is present and set in the
# provided global.env (defaults to /etc/justnews/global.env). Useful to run
# in CI or in preflight checks to ensure deployments have a canonical runtime
# configured.

GLOBAL_ENV_PATH=${1:-/etc/justnews/global.env}

if [[ ! -f "$GLOBAL_ENV_PATH" ]]; then
  echo "global.env not found at $GLOBAL_ENV_PATH"
  # As a fallback in CI, check repository example file(s)
  REPO_EXAMPLE="$(pwd)/infrastructure/systemd/examples/justnews.env.example"
  if [[ -f "$REPO_EXAMPLE" ]]; then
    echo "Checking repository example: $REPO_EXAMPLE"
    if grep -q '^PYTHON_BIN=' "$REPO_EXAMPLE"; then
      echo "OK: example file contains PYTHON_BIN"
      exit 0
    else
      echo "ERROR: example file missing PYTHON_BIN" >&2
      exit 2
    fi
  fi
  echo "ERROR: global.env not found and no example found to validate" >&2
  exit 1
fi

if grep -q '^PYTHON_BIN=' "$GLOBAL_ENV_PATH"; then
  val=$(grep '^PYTHON_BIN=' "$GLOBAL_ENV_PATH" | head -n1 | cut -d '=' -f2-)
  if [[ -n "$val" ]]; then
    echo "OK: PYTHON_BIN is set in $GLOBAL_ENV_PATH -> $val"
    # Optionally check executable exists
    if [[ -x "$val" ]]; then
      echo "Validated: $val is executable"
      exit 0
    else
      echo "WARNING: PYTHON_BIN='$val' is not executable on this host" >&2
      exit 2
    fi
  else
    echo "ERROR: PYTHON_BIN is present but empty in $GLOBAL_ENV_PATH" >&2
    exit 2
  fi
else
  echo "ERROR: PYTHON_BIN not set in $GLOBAL_ENV_PATH" >&2
  exit 2
fi
