#!/usr/bin/env bash
set -euo pipefail

# Deprecated compatibility wrapper: conda-based pytest runner has been removed.
# Forward to canonical UV/venv runner.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=/dev/null
source "$REPO_ROOT/scripts/common/deprecated_forward.sh"

deprecated_forward \
  "[DEPRECATED] scripts/dev/run_pytest_conda.sh is deprecated; using UV/venv runner (scripts/dev/pytest.sh)." \
  "$SCRIPT_DIR/pytest.sh" \
  "$@"
