#!/usr/bin/env bash
set -euo pipefail

UNIT_SRC="$(dirname "$0")/systemd/justnews-gpu-telemetry.service"
UNIT_DEST="/etc/systemd/system/justnews-gpu-telemetry.service"

# Determine defaults
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEFAULT_USER="${SUDO_USER:-$(whoami)}"
DEFAULT_GROUP="syslog"
DEFAULT_LOGDIR="/var/log/justnews-perf"
DEFAULT_PORT=9118
DEFAULT_PY_BIN="$HOME/miniconda3/envs/${CANONICAL_ENV:-justnews-py312-phase1}/bin/python"

if [ ! -f "$UNIT_SRC" ]; then
  echo "Service unit not found at $UNIT_SRC" >&2
  exit 2
fi

echo "Installing systemd unit to $UNIT_DEST (requires sudo)"
sudo cp "$UNIT_SRC" "$UNIT_DEST"
sudo chmod 644 "$UNIT_DEST"

# Ensure /etc/default has settings so the service is portable across hosts
ENV_FILE="/etc/default/justnews-gpu-telemetry"
echo "# Configuration for justnews-gpu-telemetry service" | sudo tee "$ENV_FILE" >/dev/null
echo "JN_USER=${DEFAULT_USER}" | sudo tee -a "$ENV_FILE" >/dev/null
echo "JN_GROUP=${DEFAULT_GROUP}" | sudo tee -a "$ENV_FILE" >/dev/null
echo "JN_WORKDIR=${REPO_ROOT}" | sudo tee -a "$ENV_FILE" >/dev/null
echo "JN_LOGDIR=${DEFAULT_LOGDIR}" | sudo tee -a "$ENV_FILE" >/dev/null
echo "JN_EXPORTER_PORT=${DEFAULT_PORT}" | sudo tee -a "$ENV_FILE" >/dev/null
echo "JN_PYTHON_BIN=${DEFAULT_PY_BIN:-$HOME/miniconda3/envs/${CANONICAL_ENV:-justnews-py312-phase1}/bin/python}" | sudo tee -a "$ENV_FILE" >/dev/null
echo "# Optional tuning: JN_START_UTIL / JN_START_SECONDS / JN_STOP_UTIL / JN_STOP_SECONDS" | sudo tee -a "$ENV_FILE" >/dev/null

echo "Creating log directory '$DEFAULT_LOGDIR' and adjusting ownership (requires sudo)"
sudo mkdir -p "$DEFAULT_LOGDIR"
sudo chown "$DEFAULT_USER":"$DEFAULT_GROUP" "$DEFAULT_LOGDIR" || true

sudo systemctl daemon-reload
sudo systemctl enable --now justnews-gpu-telemetry.service
echo "Service installed and started. Check status: sudo systemctl status justnews-gpu-telemetry.service"
echo "If you want to customize values, edit $ENV_FILE and run: sudo systemctl restart justnews-gpu-telemetry.service"
