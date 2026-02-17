#!/usr/bin/env bash
# gpu_watch.sh - Sample GPU metrics periodically and write JSONL
# Requires: nvidia-smi

set -euo pipefail

INTERVAL=1
DURATION=0   # 0 = infinite
OUTPUT="./gpu_watch.jsonl"
VERBOSE=false

usage() {
  cat << EOF
Usage: $0 [--interval N] [--duration N] [--output FILE] [--verbose]

  --interval N   Sample interval seconds (default: 1)
  --duration N   Total duration seconds (0=infinite, default: 0)
  --output FILE  Output JSONL file (default: ./gpu_watch.jsonl)
  --verbose      Echo samples to stdout
  -h, --help     Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL="${2:-1}"; shift 2;;
    --duration) DURATION="${2:-0}"; shift 2;;
    --output) OUTPUT="${2:-./gpu_watch.jsonl}"; shift 2;;
    --verbose) VERBOSE=true; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

if ! command -v nvidia-smi &>/dev/null; then
  echo "nvidia-smi not found; cannot sample GPU metrics" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"

START_TS=$(date -Is)
echo "# gpu_watch start_time=$START_TS interval_sec=$INTERVAL" >"$OUTPUT.tmp"

COUNT=0
END_TIME=$(( $(date +%s) + (DURATION) ))

cleanup() { mv "$OUTPUT.tmp" "$OUTPUT"; }
trap cleanup EXIT

while :; do
  now=$(date -Is)
  # GPU-level metrics
  # name, index, mem.used [MiB], mem.total [MiB], util.gpu [%], temp [C], power [W]
  gpu_csv=$(nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw \
            --format=csv,noheader,nounits 2>/dev/null || true)

  # Process metrics (may be empty). Fields: gpu_uuid, pid, process_name, used_memory [MiB]
  proc_csv=$(nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null || true)

  # Build JSON record
  json_record="{\n  \"time\": \"$now\",\n  \"gpus\": ["
  # GPUs
  IFS=$'\n' read -d '' -r -a gpu_lines <<< "${gpu_csv}" || true
  for i in "${!gpu_lines[@]}"; do
    IFS="," read -r idx name mem_used mem_total util temp power <<< "${gpu_lines[$i]}"
    idx=$(echo "$idx" | xargs)
    name=$(echo "$name" | xargs)
    mem_used=$(echo "$mem_used" | xargs)
    mem_total=$(echo "$mem_total" | xargs)
    util=$(echo "$util" | xargs)
    temp=$(echo "$temp" | xargs)
    power=$(echo "$power" | xargs)
  json_record+="${i:+,}{\"index\":$idx,\"name\":\"$name\",\"memory_used_mib\":$mem_used,\"memory_total_mib\":$mem_total,\"utilization_percent\":$util,\"temperature_c\":$temp,\"power_watts\":$power}"
  done
  json_record+="],\n  \"processes\": ["

  # Processes
  IFS=$'\n' read -d '' -r -a proc_lines <<< "${proc_csv}" || true
  added=false
  for line in "${proc_lines[@]}"; do
    [[ -z "$line" ]] && continue
    IFS="," read -r uuid pid pname pmem <<< "$line"
    pid=$(echo "$pid" | xargs)
    pname=$(echo "$pname" | xargs | sed 's/\\/\\\\/g; s/\"/\\\"/g')
    pmem=$(echo "$pmem" | xargs)
    json_record+="${added:+,}{\"pid\":$pid,\"process_name\":\"$pname\",\"used_memory_mib\":$pmem}"
    added=true
  done
  json_record+=" ]\n}"

  echo "$json_record" >>"$OUTPUT.tmp"

  $VERBOSE && echo "$json_record"

  COUNT=$((COUNT+1))
  if [[ "$DURATION" -gt 0 ]]; then
    now_s=$(date +%s)
    [[ $now_s -ge $END_TIME ]] && break
  fi
  sleep "$INTERVAL"
done
