#!/usr/bin/env bash
# Idempotent installer for Alertmanager systemd unit
# Usage: sudo ./scripts/install_alertmanager_unit.sh [--enable]

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
EXAMPLE_UNIT="$ROOT_DIR/infrastructure/systemd/alertmanager.service.example"
TARGET_UNIT="/etc/systemd/system/alertmanager.service"
BACKUP_DIR="/var/backups/justnews/alertmanager"
ENABLE=0

while [[ $# -gt 0 ]]; do
  case $1 in
    --enable) ENABLE=1; shift ;;
    -h|--help) echo "Usage: $0 [--enable]"; exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ ! -f "$EXAMPLE_UNIT" ]]; then
  echo "Example unit not found at $EXAMPLE_UNIT" >&2
  exit 1
fi

sudo mkdir -p "$BACKUP_DIR"

# If target exists compare; if identical, do nothing.
if [[ -f "$TARGET_UNIT" ]]; then
  if sudo cmp -s "$EXAMPLE_UNIT" "$TARGET_UNIT"; then
    echo "Unit file exists and is identical; no change needed"
  else
    TS=$(date +%Y%m%dT%H%M%S)
    sudo cp "$TARGET_UNIT" "$BACKUP_DIR/alertmanager.service.$TS.bak"
    echo "Backed up existing unit to $BACKUP_DIR/alertmanager.service.$TS.bak"
    sudo cp "$EXAMPLE_UNIT" "$TARGET_UNIT"
    echo "Replaced unit file at $TARGET_UNIT"
  fi
else
  sudo cp "$EXAMPLE_UNIT" "$TARGET_UNIT"
  echo "Installed unit file to $TARGET_UNIT"
fi

sudo chown root:root "$TARGET_UNIT"
sudo chmod 0644 "$TARGET_UNIT"

sudo systemctl daemon-reload

if [[ $ENABLE -eq 1 ]]; then
  sudo systemctl enable --now alertmanager.service
  echo "Enabled and started alertmanager.service"
else
  echo "Unit installed; run 'sudo systemctl enable --now alertmanager.service' to start it"
fi

# Verify status
sudo systemctl is-enabled --quiet alertmanager.service && ENABLED="enabled" || ENABLED="disabled"
STATUS=$(systemctl is-active alertmanager.service 2>/dev/null || echo "inactive")

echo "alertmanager.service is $ENABLED and $STATUS"
