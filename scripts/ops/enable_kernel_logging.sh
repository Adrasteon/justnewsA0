#!/usr/bin/env bash
# Ensure kernel/Xid events persist across reboots by enabling journald persistence
# and guaranteeing rsyslog captures the kernel facility. Requires sudo/root.

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "This script must run as root (use sudo)." >&2
  exit 1
fi

JOURNAL_DIR="/var/log/journal"
JOURNAL_CONF="/etc/systemd/journald.conf"
RSYSLOG_DROPIN="/etc/rsyslog.d/20-kernel-logging.conf"

mkdir -p "${JOURNAL_DIR}"
chmod 2755 "${JOURNAL_DIR}"
if getent group systemd-journal > /dev/null 2>&1; then
  chown root:systemd-journal "${JOURNAL_DIR}"
else
  chown root:root "${JOURNAL_DIR}"
fi

if grep -q '^Storage=' "${JOURNAL_CONF}"; then
  sed -ri 's/^Storage=.*/Storage=persistent/' "${JOURNAL_CONF}"
else
  printf '\nStorage=persistent\n' >> "${JOURNAL_CONF}"
fi

systemd-tmpfiles --create --prefix /var/log/journal
systemctl restart systemd-journald

cat <<'EOF' > "${RSYSLOG_DROPIN}"
# Ensure kernel facility messages (e.g., NVIDIA Xid resets) persist on disk
kern.*    /var/log/kern.log
& stop
EOF

if systemctl list-unit-files | grep -q '^rsyslog.service'; then
  systemctl restart rsyslog
else
  echo "rsyslog.service not found; install/enable rsyslog to capture /var/log/kern.log" >&2
fi

echo "Persistent kernel logging enabled. Check: journalctl -k -b and /var/log/kern.log"
