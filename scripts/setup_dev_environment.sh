#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$REPO_ROOT/scripts/common/deprecated_forward.sh"

deprecated_forward \
  "[DEPRECATED] scripts/setup_dev_environment.sh previously managed conda dev envs. This path is retired; JustNews uses UV/.venv. Use: make env-bootstrap" \
  "$REPO_ROOT/scripts/bootstrap_venv.sh" \
  "$@"
