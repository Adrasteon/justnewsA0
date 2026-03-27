#!/bin/bash
set -euo pipefail

export WORKFLOW_ORCHESTRATOR_PORT=${WORKFLOW_ORCHESTRATOR_PORT:-8023}
export PYTHONPATH=${PYTHONPATH:-}:.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${REPO_ROOT}/.venv/bin/python"

if [[ -x "${VENV_PY}" ]]; then
  exec "${VENV_PY}" -m uvicorn agents.workflow_orchestrator.main:app --host 0.0.0.0 --port "${WORKFLOW_ORCHESTRATOR_PORT}"
fi

exec python -m uvicorn agents.workflow_orchestrator.main:app --host 0.0.0.0 --port "${WORKFLOW_ORCHESTRATOR_PORT}"
