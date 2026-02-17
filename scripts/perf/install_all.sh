#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing JustNews GPU telemetry service + logrotate on this host"

echo "1) Installing logrotate config"
sudo "$SCRIPT_DIR/install_logrotate.sh"

echo "2) Installing systemd service and defaults"
sudo "$SCRIPT_DIR/install_service.sh"

echo "Done — telemetry service should be enabled and started"
echo "Check status: sudo systemctl status justnews-gpu-telemetry.service"
echo "If you need to tweak runtime behavior (thresholds, ports, logdir), edit /etc/default/justnews-gpu-telemetry and restart the service"
