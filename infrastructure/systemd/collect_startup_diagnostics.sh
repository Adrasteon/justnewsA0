#!/bin/bash
set -euo pipefail

# collect_startup_diagnostics.sh — gather systemd/system diagnostics to
# troubleshoot slow or stalled JustNews startups. Run as root (sudo).

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] Run this script as root (sudo)." >&2
  exit 1
fi

LOG_DIR="/var/log/justnews"
mkdir -p "$LOG_DIR"
timestamp="$(date +%Y%m%d_%H%M%S)"
log_file="$LOG_DIR/startup_diag_${timestamp}.log"

echo "[INFO] Collecting diagnostics; output will be saved to $log_file"

run_cmd() {
  local description="$1"
  shift
  echo
  echo "===== $description ====="
  if "$@"; then
    return 0
  else
    local rc=$?
    echo "[WARN] Command '$*' exited with status $rc"
    return $rc
  fi
}

{
  echo "JustNews startup diagnostics collected $(date -Iseconds)"
  echo "Host: $(hostnamectl --static || hostname)"

  run_cmd "systemctl overall state" systemctl is-system-running
  run_cmd "systemd job queue" systemctl list-jobs --no-pager
  run_cmd "failed systemd units" systemctl --failed --no-pager
  run_cmd "units stuck activating" systemctl list-units --state=activating --no-pager
  run_cmd "systemd-analyze blame" systemd-analyze blame
  run_cmd "systemd critical chain" systemd-analyze critical-chain

  run_cmd "recent high-priority journal entries (last 15m)" \
    journalctl --since "-15 min" --priority=0..3 --no-pager -o short-iso

  run_cmd "recent JustNews unit logs (last 30m)" \
    journalctl --since "-30 min" --unit 'justnews@*' -n 400 --no-pager -o short-iso

  run_cmd "recent canonical startup logs" \
    journalctl --since "-30 min" --unit justnews-canonical-startup.service -n 200 --no-pager -o short-iso

  run_cmd "coredump summary" coredumpctl list --no-pager

  run_cmd "processes in uninterruptible sleep" \
    bash -c "ps -eo pid,ppid,stat,wchan:32,%cpu,%mem,cmd | awk '$3 ~ /D/ {print}'"

  run_cmd "top CPU consumers" ps -eo pid,ppid,%cpu,%mem,cmd --sort=-%cpu | head -n 20
  run_cmd "top memory consumers" ps -eo pid,ppid,%cpu,%mem,cmd --sort=-%mem | head -n 20

  run_cmd "load average" uptime
  run_cmd "filesystem usage" df -hT
  run_cmd "filesystem inode usage" df -hi
  run_cmd "block device latency (requires iostat)" iostat -xz 1 3

  run_cmd "dmesg tail" dmesg | tail -n 200

  echo
  echo "[INFO] Diagnostics collection completed"
} 2>&1 | tee "$log_file"

echo "[INFO] Diagnostics saved to $log_file"