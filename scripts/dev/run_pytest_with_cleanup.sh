#!/usr/bin/env bash
set -euo pipefail

# Wrapper to stop local agents before running the canonical pytest runner
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo "Stopping local agents before running tests (if any)"
"${SCRIPT_DIR}/stop_local_agents.sh"

echo "Running pytest via canonical runner"
exec "${SCRIPT_DIR}/run_pytest_conda.sh" "$@"
