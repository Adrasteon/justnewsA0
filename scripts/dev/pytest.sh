#!/usr/bin/env bash
# Backwards-compatible wrapper for local pytest runs that prefer the canonical conda env
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Respect global CANONICAL_ENV if exported in environment (fallback is inside
# run_pytest_conda.sh). This wrapper simply delegates to run_pytest_conda.sh
# to ensure a single behavior for local & CI test runs.
# Run the pytest runner under scripts/run_with_env.sh so we pick up the canonical
# environment variables loaded from global.env before invoking pytest in conda.
if [[ -x "${SCRIPT_DIR}/../run_with_env.sh" ]]; then
	exec "${SCRIPT_DIR}/../run_with_env.sh" "${SCRIPT_DIR}/run_pytest_conda.sh" "$@"
else
	exec "${SCRIPT_DIR}/run_pytest_conda.sh" "$@"
fi
