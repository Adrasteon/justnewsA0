#!/usr/bin/env bash
set -euo pipefail

# Install the justnews-dev-telemetry.service unit (copy from repository to /etc/systemd/system)
REPO_ROOT="${SERVICE_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
UNIT_SRC="$REPO_ROOT/infrastructure/systemd/units/justnews-dev-telemetry.service"
UNIT_DST="/etc/systemd/system/justnews-dev-telemetry.service"

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Unit source not found: $UNIT_SRC" >&2
  exit 1
fi

sudo cp "$UNIT_SRC" "$UNIT_DST"
sudo chmod 644 "$UNIT_DST"
sudo systemctl daemon-reload
echo "Installed $UNIT_DST"

echo "To enable and start the dev telemetry service run:"
echo "  sudo systemctl enable --now justnews-dev-telemetry.service"
