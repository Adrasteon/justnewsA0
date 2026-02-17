#!/usr/bin/env bash
# Installs the repo logrotate policy to /etc/logrotate.d
set -euo pipefail
CONF="infrastructure/logrotate/justnews-gpu-monitor"
if [ ! -f "$CONF" ]; then
  echo "Missing $CONF" >&2
  exit 1
fi
sudo cp "$CONF" /etc/logrotate.d/justnews-gpu-monitor
sudo chown root:root /etc/logrotate.d/justnews-gpu-monitor
sudo chmod 0644 /etc/logrotate.d/justnews-gpu-monitor
# Test rotate once (forces rotation)
sudo logrotate -f /etc/logrotate.d/justnews-gpu-monitor || true

echo "Installed /etc/logrotate.d/justnews-gpu-monitor (you can remove it with: sudo rm /etc/logrotate.d/justnews-gpu-monitor)"
