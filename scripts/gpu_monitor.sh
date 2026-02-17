#!/usr/bin/env bash
# Simple GPU + memory monitor that appends sampling data to a log file
# Usage: scripts/gpu_monitor.sh [logfile] [interval_seconds]
# Default logfile is <repo_root>/run/gpu_monitor.log
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT_DIR/run"
mkdir -p "$RUN_DIR"
LOG=${1:-"$RUN_DIR/gpu_monitor.log"}
# ensure logfile exists and has sane perms
touch "$LOG"
chmod 0644 "$LOG"
INTERVAL=${2:-5}

echo "Starting GPU monitor: logging to $LOG (interval=${INTERVAL}s)"

while true; do
  date --iso-8601=seconds >> "$LOG"
  echo "--- nvidia-smi compute-apps ---" >> "$LOG"
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv >> "$LOG" 2>&1 || true
  echo "--- nvidia-smi summary ---" >> "$LOG"
  nvidia-smi -q -d MEMORY,TEMPERATURE,POWER >> "$LOG" 2>&1 || true
  echo "--- free -h ---" >> "$LOG"
  free -h >> "$LOG" 2>&1 || true
  echo "--- top RSS (top 20) ---" >> "$LOG"
  ps aux --sort=-rss | head -n 20 >> "$LOG" 2>&1 || true
  echo "--- vLLM unit status ---" >> "$LOG"
  if systemctl --user is-active --quiet vllm-mistral-7b.service; then
    echo "vllm-mistral-7b: active" >> "$LOG"
  else
    echo "vllm-mistral-7b: inactive" >> "$LOG"
    systemctl --user status vllm-mistral-7b.service --no-pager --lines=3 >> "$LOG" 2>&1 || true
  fi
  echo "----" >> "$LOG"
  sleep "$INTERVAL"
done
