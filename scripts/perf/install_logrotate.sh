#!/usr/bin/env bash
set -euo pipefail

CONF_SRC="$(dirname "$0")/logrotate/justnews-perf.conf"
DEST="/etc/logrotate.d/justnews-perf"

# Detect runtime user (prefer SUDO_USER when run via sudo)
DEFAULT_USER="${SUDO_USER:-$(whoami)}"
DEFAULT_LOGDIR="/var/log/justnews-perf"

if [ ! -f "$CONF_SRC" ]; then
  echo "Error: source $CONF_SRC not found" >&2
  exit 2
fi

echo "Installing logrotate config to $DEST (requires sudo)"
# Replace placeholder with real user so 'su <user> syslog' is accurate
TMP_FILE="$(mktemp)"
sed "s/@JN_USER@/${DEFAULT_USER}/g" "$CONF_SRC" > "$TMP_FILE"

sudo cp "$TMP_FILE" "$DEST"
sudo chmod 644 "$DEST"
rm -f "$TMP_FILE"

echo "Ensuring log directory exists: $DEFAULT_LOGDIR"
sudo mkdir -p "$DEFAULT_LOGDIR"
sudo chown ${DEFAULT_USER}:syslog "$DEFAULT_LOGDIR" || true

echo "Installed. You can test rotation with: sudo logrotate -d $DEST"
