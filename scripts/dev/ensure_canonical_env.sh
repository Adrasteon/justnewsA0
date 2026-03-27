#!/usr/bin/env bash
set -euo pipefail

# Ensure we are running inside the project UV/venv runtime unless explicitly bypassed.
# Bypass: ALLOW_ANY_PYTEST_ENV=1

if [[ "${ALLOW_ANY_PYTEST_ENV:-}" == "1" ]]; then
  echo "ALLOW_ANY_PYTEST_ENV=1 — skipping canonical env enforcement"
  exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
EXPECTED_PY="${VENV_DIR}/bin/python"
ACTIVE_PY="$(command -v python || true)"

if [[ -x "${EXPECTED_PY}" ]]; then
  if [[ "${ACTIVE_PY}" == "${EXPECTED_PY}" ]] || [[ "${VIRTUAL_ENV:-}" == "${VENV_DIR}" ]]; then
    echo "Canonical UV/venv is active (${VENV_DIR})"
    exit 0
  fi

  echo "Canonical UV/venv exists but is not active."
  echo "Use: source ${VENV_DIR}/bin/activate"
  echo "or run commands explicitly with: ${EXPECTED_PY} -m <module>"
  exit 0
fi

echo "ERROR: canonical UV/venv not found at ${VENV_DIR}."
echo "Create it with: make env-bootstrap"
exit 2
