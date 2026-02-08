#!/usr/bin/env bash
set -euo pipefail

# Ensure we are running inside the canonical conda environment (CANONICAL_ENV)
# or that the canonical environment exists. Exits non-zero if the check fails
# and ALLOW_ANY_PYTEST_ENV is not set to 1.

CANONICAL_ENV=${CANONICAL_ENV:-justnews-py312}

if [[ "${ALLOW_ANY_PYTEST_ENV:-}" == "1" ]]; then
  echo "ALLOW_ANY_PYTEST_ENV=1 — skipping canonical env enforcement"
  exit 0
fi

echo "Checking canonical conda environment: $CANONICAL_ENV"

active_env="${CONDA_DEFAULT_ENV:-}"
if [[ -n "$active_env" && "$active_env" == "$CANONICAL_ENV" ]]; then
  echo "Canonical conda env '$CANONICAL_ENV' is active (CONDA_DEFAULT_ENV=$active_env)"
  exit 0
fi

# If not active, check if that environment exists and prefer running via conda run
if command -v conda >/dev/null 2>&1; then
  if conda env list 2>/dev/null | awk '{print $1}' | grep -xq "$CANONICAL_ENV"; then
    echo "Canonical env exists but is not active. Prefer running with: conda run -n $CANONICAL_ENV <command>"
    exit 0
  fi
fi

echo "ERROR: canonical conda env '$CANONICAL_ENV' not active or not present."
echo "Please create or activate it, or set ALLOW_ANY_PYTEST_ENV=1 to bypass this check."
exit 2
