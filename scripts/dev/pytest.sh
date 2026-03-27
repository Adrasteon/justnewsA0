#!/usr/bin/env bash
# Local pytest wrapper that prefers project UV/venv (.venv).
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/../.." && pwd)
VENV_PY="${REPO_ROOT}/.venv/bin/python"

if [[ -x "${VENV_PY}" ]]; then
  exec "${VENV_PY}" -m pytest "$@"
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --directory "${REPO_ROOT}" pytest "$@"
fi

if command -v pytest >/dev/null 2>&1; then
  exec pytest "$@"
fi

echo "ERROR: pytest is unavailable. Create the UV environment first (make env-bootstrap)." >&2
exit 2
