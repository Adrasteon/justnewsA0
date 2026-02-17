#!/bin/bash
# cold_start.sh — One-command cold boot for JustNews after machine restart
# Ensures prerequisites, enables units, starts orchestrator, starts all services, verifies health.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_ROOT="$SCRIPT_DIR"
PROJECT_ROOT="$(cd "$SYSTEMD_ROOT/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $*"; }
ok() { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[ERROR]${NC} $*"; }

require_root() {
  if [[ $EUID -ne 0 ]]; then fail "Run as root (sudo)"; exit 1; fi
}

check_tools() {
  local req=(systemctl curl ss)
  for t in "${req[@]}"; do
    command -v "$t" >/dev/null 2>&1 || { fail "Missing tool: $t"; exit 1; }
  done
}

ensure_path_wrappers() {
  # Install/refresh operator PATH wrappers (idempotent)
  local dsts=(
    "/usr/local/bin/enable_all.sh"
    "/usr/local/bin/health_check.sh"
    "/usr/local/bin/reset_and_start.sh"
    "/usr/local/bin/cold_start.sh"
  )
  local srcs=(
    "$SYSTEMD_ROOT/scripts/enable_all.sh"
    "$SYSTEMD_ROOT/scripts/health_check.sh"
    "$SYSTEMD_ROOT/scripts/reset_and_start.sh"
    "$SYSTEMD_ROOT/scripts/cold_start.sh"
  )
  for i in "${!dsts[@]}"; do
    local dst="${dsts[$i]}"; local src="${srcs[$i]}"
    if [[ -f "$src" ]]; then
      if [[ ! -f "$dst" ]] || ! cmp -s "$src" "$dst"; then
        cp "$src" "$dst" && chmod +x "$dst" && ok "Installed/updated PATH wrapper $(basename "$dst")"
      fi
    fi
  done
}

ensure_install_helpers() {
  # Install/refresh helper scripts (idempotent)
  local start_dst="/usr/local/bin/justnews-start-agent.sh"
  local start_src="$SYSTEMD_ROOT/scripts/justnews-start-agent.sh"
  local wait_dst="/usr/local/bin/wait_for_mcp.sh"
  local wait_src="$SYSTEMD_ROOT/scripts/wait_for_mcp.sh"
  local smoke_dst="/usr/local/bin/justnews-boot-smoke.sh"
  local smoke_src="$SYSTEMD_ROOT/scripts/justnews-boot-smoke.sh"
  local preflight_dst="/usr/local/bin/justnews-preflight-check.sh"
  local preflight_src="$SYSTEMD_ROOT/scripts/justnews-preflight-check.sh"
  for pair in "$start_src|$start_dst" "$wait_src|$wait_dst" "$smoke_src|$smoke_dst" "$preflight_src|$preflight_dst"; do
    IFS='|' read -r src dst <<<"$pair"
    if [[ -f "$src" ]]; then
      if [[ ! -f "$dst" ]] || ! cmp -s "$src" "$dst"; then
        cp "$src" "$dst" && chmod +x "$dst" && ok "Installed/updated $dst"
      fi
    fi
  done
}

ensure_unit_template() {
  local unit_dst="/etc/systemd/system/justnews@.service"
  local unit_src="$SYSTEMD_ROOT/units/justnews@.service"
  if [[ -f "$unit_src" ]]; then
    if [[ ! -f "$unit_dst" ]] || ! cmp -s "$unit_src" "$unit_dst"; then
      cp "$unit_src" "$unit_dst"
      systemctl daemon-reload
      ok "Installed/updated unit template"
    fi
  fi
}


wait_http() {
  local url="$1"; local timeout="${2:-120}"; local i=0
  while (( i < timeout )); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then return 0; fi
    sleep 1; ((i++))
  done
  return 1
}

cold_start() {
  log "Enabling all JustNews units"
  "$SCRIPT_DIR/enable_all.sh" enable || true

  log "Starting GPU Orchestrator"
  systemctl start justnews@gpu_orchestrator
  if ! "$SCRIPT_DIR/enable_all.sh" status >/dev/null 2>&1; then :; fi
  if ! wait_http "http://127.0.0.1:8014/ready" 180; then
    fail "gpu_orchestrator did not become READY within timeout"; return 1
  fi
  ok "gpu_orchestrator READY"

  log "Starting all services"
  "$SCRIPT_DIR/enable_all.sh" start

  log "Running health check"
  if "$SCRIPT_DIR/health_check.sh"; then
    ok "All services healthy"
  else
    warn "Health check reported issues"; return 2
  fi
}

main() {
  require_root
  check_tools
  ensure_unit_template
  ensure_install_helpers
  ensure_path_wrappers
  cold_start
}

main "$@"
