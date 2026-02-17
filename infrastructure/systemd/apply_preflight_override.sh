#!/usr/bin/env bash
# apply_preflight_override.sh
# Helper to apply preflight ExecStartPre drop-in to selected instances.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OVERRIDE_SRC="${SCRIPT_DIR}/units/overrides/10-preflight-gating.conf"

usage(){
  cat <<EOF
Usage: $(basename "$0") <instance1> [instance2 ...]

Examples:
  $(basename "$0") gpu_orchestrator
  $(basename "$0") gpu_orchestrator analyst scout
EOF
}

if [[ $# -lt 1 ]]; then
  usage; exit 1
fi

if [[ ! -f "$OVERRIDE_SRC" ]]; then
  echo "Override template not found: $OVERRIDE_SRC" >&2
  exit 1
fi

for inst in "$@"; do
  dst_dir="/etc/systemd/system/justnews@${inst}.service.d"
  sudo mkdir -p "$dst_dir"
  sudo cp "$OVERRIDE_SRC" "$dst_dir/10-preflight-gating.conf"
  echo "Applied preflight override to instance: $inst"
done

echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Done. You can verify with: systemd-analyze verify /etc/systemd/system/justnews@<instance>.service"
