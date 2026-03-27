#!/usr/bin/env bash
# Shared helpers for JustNews systemd scripts.
# Source from operational scripts to avoid duplicated logging/color/env boilerplate.

# ANSI colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Source env file and export all variables loaded from it.
source_env_file_exported() {
  local env_path="$1"
  if [[ ! -f "$env_path" ]]; then
    return 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$env_path"
  set +a
}

# Resolve first available Python binary candidate.
# Accepts absolute paths and command names.
resolve_python_bin() {
  local candidate=""
  for candidate in "$@"; do
    [[ -z "$candidate" ]] && continue
    if [[ "$candidate" == */* ]]; then
      if [[ -x "$candidate" ]]; then
        echo "$candidate"
        return 0
      fi
    else
      if command -v "$candidate" >/dev/null 2>&1; then
        command -v "$candidate"
        return 0
      fi
    fi
  done
  return 1
}
