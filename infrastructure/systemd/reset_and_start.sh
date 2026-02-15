#!/bin/bash
# reset_and_start.sh — Canonical reset/start script for JustNews (systemd)
#
# Performs a safe, end-to-end reset:
# - Stops and disables services
# - Frees occupied ports
# - Optionally reinstalls unit template and helper scripts
# - Optionally syncs env files to /etc/justnews
# - Optionally toggles SAFE_MODE in global.env
# - Reloads systemd and fresh-starts all services
# - Runs a health check summary at the end

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

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Defaults
REINSTALL=false
REINSTALL_UNITS=false
REINSTALL_SCRIPTS=false
SYNC_ENV=false
FORCE_SYNC_ENV=false
SAFE_MODE_STATE=""   # "on" | "off" | ""
CLEAN_PORTS=true
HEALTH_CHECK=true
DRY_RUN=false

PORTS=(8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8012 8013 8014 8015 8016)
UNIT_TEMPLATE_SRC="$SYSTEMD_ROOT/units/justnews@.service"
UNIT_TEMPLATE_DST="/etc/systemd/system/justnews@.service"
START_SCRIPT_SRC="$SYSTEMD_ROOT/scripts/justnews-start-agent.sh"
START_SCRIPT_DST="/usr/local/bin/justnews-start-agent.sh"
WAIT_SCRIPT_SRC="$SYSTEMD_ROOT/scripts/wait_for_mcp.sh"
WAIT_SCRIPT_DST="/usr/local/bin/wait_for_mcp.sh"
PRECHECK_SCRIPT_SRC="$SYSTEMD_ROOT/scripts/justnews-preflight-check.sh"
PRECHECK_SCRIPT_DST="/usr/local/bin/justnews-preflight-check.sh"
ENV_SRC_DIR="$SYSTEMD_ROOT/examples"
ENV_DST_DIR="/etc/justnews"
GLOBAL_ENV="$ENV_DST_DIR/global.env"
WRAPPER_MAP=(
  "/usr/local/bin/enable_all.sh|$SYSTEMD_ROOT/scripts/enable_all.sh"
  "/usr/local/bin/health_check.sh|$SYSTEMD_ROOT/scripts/health_check.sh"
  "/usr/local/bin/reset_and_start.sh|$SYSTEMD_ROOT/scripts/reset_and_start.sh"
  "/usr/local/bin/cold_start.sh|$SYSTEMD_ROOT/scripts/cold_start.sh"
)

require_root() {
  if [[ $EUID -ne 0 ]]; then
    log_error "Must run as root (sudo)"
    exit 1
  fi
}

check_tools() {
  local req=(systemctl ss cp sed grep awk)
  for t in "${req[@]}"; do
    if ! command -v "$t" &>/dev/null; then
      log_error "Required tool missing: $t"; exit 1
    fi
  done
}

usage() {
  cat << EOF
Usage: $0 [options]

Options:
  --reinstall            Reinstall unit template and helper scripts
  --reinstall-units      Reinstall only systemd unit template
  --reinstall-scripts    Reinstall only helper scripts
  --sync-env             Copy env files to /etc/justnews (no overwrite)
  --force-sync-env       Copy env files and overwrite existing (with .bak)
  --safe-mode on|off     Toggle SAFE_MODE in /etc/justnews/global.env
  --no-clean-ports       Do not kill residual port listeners
  --no-health-check      Skip final health check
  --dry-run              Show actions without executing system changes
  -h, --help             Show this help

Examples:
  sudo $0 --reinstall --sync-env --safe-mode on
  sudo $0 --force-sync-env --safe-mode off
  sudo $0  # default: clean ports + fresh start + health check
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --reinstall) REINSTALL=true; shift ;;
      --reinstall-units) REINSTALL_UNITS=true; shift ;;
      --reinstall-scripts) REINSTALL_SCRIPTS=true; shift ;;
      --sync-env) SYNC_ENV=true; shift ;;
      --force-sync-env) SYNC_ENV=true; FORCE_SYNC_ENV=true; shift ;;
      --safe-mode)
        SAFE_MODE_STATE="${2:-}"; shift 2 || true
        if [[ "$SAFE_MODE_STATE" != "on" && "$SAFE_MODE_STATE" != "off" ]]; then
          log_error "--safe-mode requires 'on' or 'off'"; exit 1
        fi
        ;;
      --no-clean-ports) CLEAN_PORTS=false; shift ;;
      --no-health-check) HEALTH_CHECK=false; shift ;;
      --dry-run) DRY_RUN=true; shift ;;
      -h|--help) usage; exit 0 ;;
      *) log_error "Unknown option: $1"; usage; exit 1 ;;
    esac
  done

  if [[ "$REINSTALL" == true ]]; then
    REINSTALL_UNITS=true; REINSTALL_SCRIPTS=true
  fi
}

backup_file() {
  local f="$1"
  if [[ -f "$f" ]]; then
    local ts
    ts="$(date +%Y%m%d_%H%M%S)"
    cp -a "$f" "${f}.bak_${ts}"
    log_info "Backed up $(basename "$f") -> ${f}.bak_${ts}"
  fi
}

stop_disable_services() {
  log_info "Stopping and disabling all JustNews services..."
  if [[ "$DRY_RUN" == true ]]; then
    echo "DRY-RUN: $SCRIPT_DIR/enable_all.sh stop/disable"; return 0
  fi
  "$SYSTEMD_ROOT/scripts/enable_all.sh" stop || true
  "$SYSTEMD_ROOT/scripts/enable_all.sh" disable || true
}

kill_ports() {
  [[ "$CLEAN_PORTS" == true ]] || { log_info "Skipping port cleanup"; return 0; }
  log_info "Cleaning residual listeners on ports: ${PORTS[*]}"
  for p in "${PORTS[@]}"; do
    local lines
    lines=$(ss -ltnp "sport = :$p" 2>/dev/null | tail -n +2 || true)
    if [[ -n "$lines" ]]; then
      log_warn "Port $p in use; attempting to kill owning processes"
      # Extract PIDs from 'users:("proc",pid=123,fd=...)'
      local pids
      pids=$(echo "$lines" | grep -oP 'pid=\K[0-9]+' | sort -u)
      if [[ -n "$pids" ]]; then
        for pid in $pids; do
          if [[ "$DRY_RUN" == true ]]; then
            echo "DRY-RUN: kill -9 $pid (port $p)"
          else
            kill -9 "$pid" 2>/dev/null || true
            log_info "Killed PID $pid (port $p)"
          fi
        done
      fi
    else
      log_success "Port $p is free"
    fi
  done
}

reinstall_units_scripts() {
  if [[ "$REINSTALL_UNITS" == true ]]; then
    log_info "Reinstalling systemd unit template..."
    if [[ "$DRY_RUN" == true ]]; then
      echo "DRY-RUN: cp $UNIT_TEMPLATE_SRC $UNIT_TEMPLATE_DST && systemctl daemon-reload"
    else
      mkdir -p "$(dirname "$UNIT_TEMPLATE_DST")"
      backup_file "$UNIT_TEMPLATE_DST"
      cp "$UNIT_TEMPLATE_SRC" "$UNIT_TEMPLATE_DST"
      systemctl daemon-reload
      log_success "Unit template installed"
    fi
  fi

  if [[ "$REINSTALL_SCRIPTS" == true ]]; then
    log_info "Reinstalling helper scripts..."
    if [[ "$DRY_RUN" == true ]]; then
      echo "DRY-RUN: cp $START_SCRIPT_SRC $START_SCRIPT_DST; cp $WAIT_SCRIPT_SRC $WAIT_SCRIPT_DST; cp $PRECHECK_SCRIPT_SRC $PRECHECK_SCRIPT_DST"
    else
      backup_file "$START_SCRIPT_DST" || true
      cp "$START_SCRIPT_SRC" "$START_SCRIPT_DST"
      chmod +x "$START_SCRIPT_DST"
      backup_file "$WAIT_SCRIPT_DST" || true
      cp "$WAIT_SCRIPT_SRC" "$WAIT_SCRIPT_DST"
      chmod +x "$WAIT_SCRIPT_DST"
      if [[ -f "$PRECHECK_SCRIPT_SRC" ]]; then
        backup_file "$PRECHECK_SCRIPT_DST" || true
        cp "$PRECHECK_SCRIPT_SRC" "$PRECHECK_SCRIPT_DST"
        chmod +x "$PRECHECK_SCRIPT_DST"
      fi
      log_success "Helper scripts installed"
    fi
  fi
}

ensure_path_wrappers() {
  # Always ensure operator PATH wrappers exist (idempotent)
  for pair in "${WRAPPER_MAP[@]}"; do
    IFS='|' read -r dst src <<<"$pair"
    if [[ -f "$src" ]] && [[ ! -x "$dst" ]]; then
      cp "$src" "$dst" && chmod +x "$dst"
      log_info "Installed PATH wrapper $(basename "$dst")"
    fi
  done
}

sync_env_files() {
  [[ "$SYNC_ENV" == true ]] || return 0
  log_info "Syncing env files to $ENV_DST_DIR (force: $FORCE_SYNC_ENV)"
  if [[ "$DRY_RUN" == true ]]; then
    echo "DRY-RUN: mkdir -p $ENV_DST_DIR; copy env files"
    return 0
  fi
  mkdir -p "$ENV_DST_DIR"
  shopt -s nullglob
  for f in "$ENV_SRC_DIR"/*.env "$ENV_SRC_DIR"/*.env.example; do
    local base
    base="$(basename "$f")"
    local dst_name="$base"
    if [[ "$base" == *.env.example ]]; then
      dst_name="${base%.env.example}.env"
    fi
    local dst="$ENV_DST_DIR/$dst_name"
    if [[ -f "$dst" && "$FORCE_SYNC_ENV" == true ]]; then
      backup_file "$dst"
      cp "$f" "$dst"
      log_info "Overwrote $dst (backup created)"
    elif [[ -f "$dst" && "$FORCE_SYNC_ENV" == false ]]; then
      log_warn "$dst exists; skipping (use --force-sync-env to overwrite)"
    else
      cp "$f" "$dst"; log_info "Copied $dst"
    fi
  done
  shopt -u nullglob

  # After syncing environment files, ensure special directories referenced by env exist
  # Load the (possibly new) global env to resolve values if present
  if [[ -f "$GLOBAL_ENV" ]]; then
    # shellcheck disable=SC1090
    . "$GLOBAL_ENV"
  fi

  if [[ -n "${CRAWL4AI_MODEL_CACHE_DIR:-}" ]]; then
    log_info "Ensuring CRAWL4AI model cache directory: $CRAWL4AI_MODEL_CACHE_DIR"
    if [[ "$DRY_RUN" == true ]]; then
      echo "DRY-RUN: mkdir -p $CRAWL4AI_MODEL_CACHE_DIR"
    else
      mkdir -p "$CRAWL4AI_MODEL_CACHE_DIR"
      chown justnews:justnews "$CRAWL4AI_MODEL_CACHE_DIR" 2>/dev/null || true
    fi
  fi
}

toggle_safe_mode() {
  [[ -n "$SAFE_MODE_STATE" ]] || return 0
  if [[ ! -f "$GLOBAL_ENV" ]]; then
    log_warn "$GLOBAL_ENV not found; creating new"
    mkdir -p "$ENV_DST_DIR"
    echo "# Auto-created by reset_and_start.sh" > "$GLOBAL_ENV"
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "DRY-RUN: Toggle SAFE_MODE=$SAFE_MODE_STATE in $GLOBAL_ENV"
    return 0
  fi
  backup_file "$GLOBAL_ENV"
  if grep -q '^SAFE_MODE=' "$GLOBAL_ENV"; then
    sed -i "s/^SAFE_MODE=.*/SAFE_MODE=$([[ "$SAFE_MODE_STATE" == on ]] && echo true || echo false)/" "$GLOBAL_ENV"
  else
    echo "SAFE_MODE=$([[ "$SAFE_MODE_STATE" == on ]] && echo true || echo false)" >> "$GLOBAL_ENV"
  fi
  log_success "SAFE_MODE set to $SAFE_MODE_STATE"
}

daemon_reload() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "DRY-RUN: systemctl daemon-reload"; return 0
  fi
  systemctl daemon-reload
}

fresh_start() {
  log_info "Starting all services fresh..."
  if [[ "$DRY_RUN" == true ]]; then
    echo "DRY-RUN: $SCRIPT_DIR/enable_all.sh fresh"; return 0
  fi
  "$SYSTEMD_ROOT/scripts/enable_all.sh" fresh
}

health_check() {
  [[ "$HEALTH_CHECK" == true ]] || return 0
  if [[ "$DRY_RUN" == true ]]; then
    echo "DRY-RUN: $SCRIPT_DIR/health_check.sh"; return 0
  fi
  if [[ -x "$SYSTEMD_ROOT/scripts/health_check.sh" ]]; then
    "$SYSTEMD_ROOT/scripts/health_check.sh" || log_warn "Health check reported issues"
  else
    log_warn "health_check.sh not found/executable"
  fi
}

main() {
  parse_args "$@"
  require_root
  check_tools

  echo "========================================"
  log_info "JustNews Canonical Reset & Start"
  echo "========================================"

  stop_disable_services
  kill_ports
  reinstall_units_scripts
  ensure_path_wrappers
  sync_env_files
  toggle_safe_mode
  daemon_reload
  fresh_start
  health_check

  log_success "Reset & start sequence completed"
}

main "$@"
