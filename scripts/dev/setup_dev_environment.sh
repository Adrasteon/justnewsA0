#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=/dev/null
source "$REPO_ROOT/scripts/common/deprecated_forward.sh"

deprecated_forward \
  "[DEPRECATED] scripts/dev/setup_dev_environment.sh managed conda/phased envs. Phased conda environments are retired. Use: make env-bootstrap" \
  "$REPO_ROOT/scripts/bootstrap_venv.sh" \
  "$@"
