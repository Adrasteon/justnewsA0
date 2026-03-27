#!/usr/bin/env bash
set -euo pipefail

# Shared helper for deprecated compatibility wrappers.
# Usage:
#   source deprecated_forward.sh
#   deprecated_forward "message" "/absolute/path/to/target" "$@"

deprecated_forward() {
  if [[ $# -lt 2 ]]; then
    echo "deprecated_forward requires: <message> <target> [args...]" >&2
    return 2
  fi

  local message="$1"
  local target="$2"
  shift 2

  echo "$message" >&2

  if [[ ! -x "$target" ]]; then
    echo "ERROR: target script is not executable: $target" >&2
    return 127
  fi

  exec "$target" "$@"
}
