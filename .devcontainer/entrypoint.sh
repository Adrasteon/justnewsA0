#!/usr/bin/env bash
set -euo pipefail

# If a venv exists in /deps/.venv, prepend it to PATH so commands use that environment.
if [ -d /deps/.venv ]; then
  export PATH="/deps/.venv/bin:$PATH"
fi

exec "$@"
