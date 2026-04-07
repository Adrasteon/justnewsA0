#!/usr/bin/env bash
# Canonical app lifecycle wrapper: Docker-first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/ops/docker_compose.sh" up "$@"
