#!/usr/bin/env bash
set -euo pipefail

# Deprecated compatibility wrapper: conda bootstrap removed in favor of UV/venv.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$REPO_ROOT/scripts/common/deprecated_forward.sh"

deprecated_forward \
  "[DEPRECATED] conda bootstrap has been removed. Forwarding to scripts/bootstrap_venv.sh." \
  "$REPO_ROOT/scripts/bootstrap_venv.sh" \
  "$@"
