#!/usr/bin/env bash
# Collect diagnostics for JustNews services into a timestamped folder
set -euo pipefail
OUT_ROOT="${1:-./justnews_diag}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$OUT_ROOT/diag_$TS"
mkdir -p "$OUT_DIR/logs" "$OUT_DIR/status"
# Save service list (order consistent with health_check)
services=(mcp_bus chief_editor fact_checker analyst synthesizer critic memory reasoning newsreader analytics archive dashboard gpu_orchestrator)
printf "%s\n" "${services[@]}" > "$OUT_DIR/services.txt"
# Systemctl status and last 200 logs
for s in "${services[@]}"; do
  systemctl status "justnews@$s" --no-pager > "$OUT_DIR/status/$s.status.txt" 2>&1 || true
  journalctl -u "justnews@$s" -n 200 --no-pager > "$OUT_DIR/logs/$s.journal.txt" 2>&1 || true
done
# Ports snapshot
ss -ltn > "$OUT_DIR/ports.txt" 2>&1 || true
# Health snapshots
for s in "${services[@]}"; do
  case "$s" in
    gpu_orchestrator)
      curl -s http://127.0.0.1:8014/health > "$OUT_DIR/$s.health.json" 2>/dev/null || true
      curl -s http://127.0.0.1:8014/ready > "$OUT_DIR/$s.ready.txt" 2>/dev/null || true
      curl -s http://127.0.0.1:8014/models/status > "$OUT_DIR/$s.models.json" 2>/dev/null || true
      ;;
    mcp_bus)
      curl -s http://127.0.0.1:8000/health > "$OUT_DIR/$s.health.json" 2>/dev/null || true
      ;;
    *)
      # generic mapping aligns with health_check.sh table
      ;;
  esac
done
# Optional GPU snapshot
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi > "$OUT_DIR/nvidia-smi.txt" 2>&1 || true
fi
echo "Diagnostics written to: $OUT_DIR"
