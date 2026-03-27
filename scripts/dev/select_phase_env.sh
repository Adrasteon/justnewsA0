#!/usr/bin/env bash
set -euo pipefail

echo "[DEPRECATED] phased conda environments are retired." >&2
echo "Use the project UV environment instead:" >&2
echo "  make env-bootstrap" >&2
echo "  source .venv/bin/activate" >&2
exit 2
