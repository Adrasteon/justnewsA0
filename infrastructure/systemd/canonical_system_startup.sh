#!/bin/bash
# canonical_system_startup.sh — End-to-end JustNews bring-up helper
# Ensures environment prerequisites, verifies database connectivity,
# validates the shared data mount, and delegates to reset_and_start.sh to
# restart all services followed by a consolidated health check.
#
# Options:
#   stop / --stop / --shutdown Stop all services and monitoring without health checks
#   --dry-run / --check-only   Run prerequisite checks without restarting services
#   --help                     Display usage information

set -euo pipefail

GLOBAL_ENV_DEFAULT="/etc/justnews/global.env"
DATA_MOUNT_DEFAULT="/media/$(whoami)/Data"
RESET_SCRIPT_NAME="reset_and_start.sh"
HEALTH_SCRIPT_NAME="health_check.sh"
MONITORING_INSTALL_RELATIVE_PATH="scripts/install_monitoring_stack.sh"

DRY_RUN=false
REQUEST_STOP=false
SHOW_USAGE=false
declare -a FORWARDED_ARGS=()

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Preferred conda env for Python helpers (default to canonical name when present)
DEFAULT_CONDA_ENV="${CANONICAL_ENV:-justnews-py312-phase1}"
CONDA_ENV="${CONDA_ENV:-$DEFAULT_CONDA_ENV}"

# Helper: run a python script using conda run -n ${CONDA_ENV} when available;
# otherwise fallback to PYTHON_BIN if configured, or system python.
run_python_script() {
  local script_path="$1"; shift || true
  if command -v conda >/dev/null 2>&1; then
    PYTHONPATH=. conda run -n "$CONDA_ENV" python "$script_path" "$@"
  elif [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
    PYTHONPATH=. "$PYTHON_BIN" "$script_path" "$@"
  else
    PYTHONPATH=. python "$script_path" "$@"
  fi
}

usage() {
  cat <<EOF
Usage: canonical_system_startup.sh [--dry-run] [reset_and_start.sh options...]

Performs environment, storage, and database checks, then restarts all JustNews
systemd services via reset_and_start.sh followed by a health summary.

Options:
  stop, --stop, --shutdown  Stop all JustNews services and monitoring stack.
  --dry-run, --check-only  Validate prerequisites only; do not restart services.
  --help                   Show this message and exit.

All unrecognised options are forwarded directly to reset_and_start.sh.
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      stop|--stop|--shutdown)
        REQUEST_STOP=true
        shift
        ;;
      --dry-run|--check-only)
        DRY_RUN=true
        shift
        ;;
      --help|-h)
        SHOW_USAGE=true
        shift
        ;;
      *)
        FORWARDED_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

require_root() {
  if [[ $EUID -ne 0 ]]; then
    # Allow non-root for dry-run checks to enable operator validation without
    # requiring root privileges. If DRY_RUN is not set, require root as before.
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
      log_warn "Not running as root — continuing because --dry-run was requested"
      return 0
    fi
    log_error "Run this script as root (sudo)."
    exit 1
  fi
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_error "Required command '$cmd' not found in PATH."
    exit 1
  fi
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local candidate

  if [[ -n "${JUSTNEWS_ROOT:-}" && -d "$JUSTNEWS_ROOT/agents" ]]; then
    echo "$JUSTNEWS_ROOT"
    return 0
  fi
  if [[ -n "${SERVICE_DIR:-}" && -d "$SERVICE_DIR/agents" ]]; then
    echo "$SERVICE_DIR"
    return 0
  fi
  candidate="$(cd "$script_dir/.." && pwd)"
  if [[ -d "$candidate/agents" ]]; then
    echo "$candidate"
    return 0
  fi
  # Emit warning to stderr so callers capturing stdout (e.g., when assigning
  # the output to a variable) do not receive the warning text as part of the
  # repo root value.
  log_warn "Falling back to repository default path." >&2
  echo "${SERVICE_DIR:-$HOME/JustNews}"
}

load_environment() {
  local env_path="${GLOBAL_ENV:-$GLOBAL_ENV_DEFAULT}"
  if [[ ! -f "$env_path" ]]; then
    log_error "Global environment file not found at $env_path"
    exit 1
  fi
  log_info "Loading global environment from $env_path"
  # shellcheck disable=SC1090
  set -a; source "$env_path"; set +a
}

ensure_env_value() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" ]]; then
    log_error "Required environment variable $name is empty after loading global.env"
    exit 1
  fi
}

check_python_runtime() {
  local python_path="${PYTHON_BIN:-}"
  if [[ ! -x "$python_path" ]]; then
    log_error "Configured PYTHON_BIN '$python_path' does not exist or is not executable"
    exit 1
  fi
  if ! python_version="$($python_path --version 2>&1)"; then
    log_error "Unable to execute PYTHON_BIN ('$python_path --version' failed)"
    exit 1
  fi
  log_success "Python runtime detected: $python_version"
  if [[ "$python_path" != *"${CONDA_ENV:-$DEFAULT_CONDA_ENV}"* ]]; then
   log_warn "PYTHON_BIN path does not reference the expected environment (${CONDA_ENV:-$DEFAULT_CONDA_ENV}); confirm the correct environment is targeted"
  fi
}

check_data_mount() {
  # Ensure required model/cache directories exist (no mount check required)
  if [[ -n "${MODEL_STORE_ROOT:-}" ]]; then
    mkdir -p "$MODEL_STORE_ROOT"
    log_info "Ensured MODEL_STORE_ROOT directory $MODEL_STORE_ROOT exists"
    chown justnews:justnews "$MODEL_STORE_ROOT" 2>/dev/null || true
  fi
  if [[ -n "${BASE_MODEL_DIR:-}" ]]; then
    mkdir -p "$BASE_MODEL_DIR"
    log_info "Ensured BASE_MODEL_DIR directory $BASE_MODEL_DIR exists"
    chown justnews:justnews "$BASE_MODEL_DIR" 2>/dev/null || true
  fi

  # Ensure Crawl4AI model cache directory exists if configured
  if [[ -n "${CRAWL4AI_MODEL_CACHE_DIR:-}" ]]; then
    mkdir -p "$CRAWL4AI_MODEL_CACHE_DIR"
    log_info "Ensured CRAWL4AI_MODEL_CACHE_DIR directory $CRAWL4AI_MODEL_CACHE_DIR exists"
    # Try to set ownership to justnews user; do not fail if chown cannot run
    chown justnews:justnews "$CRAWL4AI_MODEL_CACHE_DIR" 2>/dev/null || true
  fi
}

# Check MariaDB connectivity (host/managed DB expected in normal deployments).
# This probe is optional but recommended; it tries the "mysql" client first and
# falls back to a small Python check via PYTHON_BIN if available. The probe will
# be skipped when MARIADB_HOST is not configured or when SKIP_MARIADB_CHECK=true.
# If MARIADB_CHECK_REQUIRED=true then a failing probe will abort startup.
check_mariadb_connectivity() {
  if [[ "${SKIP_MARIADB_CHECK:-false}" == "true" ]]; then
    log_info "Skipping MariaDB connectivity check (SKIP_MARIADB_CHECK=true)"
    return 0
  fi

  if [[ -z "${MARIADB_HOST:-}" ]]; then
    log_info "MARIADB_HOST not set; skipping MariaDB connectivity check"
    return 0
  fi

  local host="${MARIADB_HOST:-localhost}"
  local port="${MARIADB_PORT:-3306}"
  local user="${MARIADB_USER:-justnews}"
  local pass="${MARIADB_PASSWORD:-}"
  local db="${MARIADB_DB:-justnews}"

  log_info "Checking MariaDB connectivity to ${host}:${port} (db=${db})"

  # Helper: report failure and potentially abort
  _handle_fail() {
    local rc=$1 msg="$2"
    log_error "MariaDB connectivity check failed: ${msg} (rc=${rc})"
    if [[ "${MARIADB_CHECK_REQUIRED:-false}" == "true" ]]; then
      exit 1
    fi
    return 0
  }

  # Try using mysql client if present
  if command -v mysql >/dev/null 2>&1; then
    if timeout 5 mysql -h "${host}" -P "${port}" -u "${user}" -p"${pass}" -e "SELECT 1;" "${db}" >/dev/null 2>&1; then
      log_success "MariaDB probe succeeded using mysql client"
      return 0
    else
      _handle_fail $? "mysql client failed to connect or run query"
      return 0
    fi
  fi

  # Fallback: try using PYTHON_BIN (if present) and pymysql
  if [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
    if ${PYTHON_BIN} - <<PYTHON >/dev/null 2>&1
import sys
try:
    import pymysql
except Exception:
    sys.exit(2)
try:
    conn = pymysql.connect(host='${host}', port=${port}, user='${user}', password='${pass}', database='${db}', connect_timeout=5)
    cur = conn.cursor()
    cur.execute('SELECT 1')
    conn.close()
    sys.exit(0)
except Exception as e:
    print('err:'+str(e))
    sys.exit(3)
PYTHON
    then
      log_success "MariaDB probe succeeded using PYTHON_BIN"
      return 0
    else
      # We get rc 2 if pymysql isn't available, 3 for connection errors
      _handle_fail $? "python pymysql probe failed (pymysql may be missing or connection failed)"
      return 0
    fi
  fi

  log_warn "No mysql client or usable PYTHON_BIN+pymysql available; skipping MariaDB probe"
  log_info "To enable the probe install 'mysql-client' on the host or ensure PYTHON_BIN points to a Python interpreter with 'pymysql' installed (pip install pymysql)"
  return 0
}

# Ensure local databases (MariaDB, ChromaDB) are active if installed as systemd units.
# This ensures a "single point of entry" for cold-start scenarios.
ensure_local_databases() {
  local dbs=("mariadb.service" "chromadb.service")

  for db in "${dbs[@]}"; do
    if systemctl list-unit-files "$db" >/dev/null 2>&1; then
      if ! systemctl is-active --quiet "$db"; then
        log_warn "Local $db is not running. Attempting to start..."
        if [[ "${DRY_RUN:-false}" == "true" ]]; then
          log_info "[DRY-RUN] Would execute: systemctl start $db"
        else
          if systemctl start "$db"; then
             log_success "Started $db"
             # Brief pause to allow init
             sleep 2
          else
             log_error "Failed to start $db"
             # If it's ChromaDB, this is likely fatal for the system
             if [[ "$db" == "chromadb.service" ]]; then
                exit 1
             fi
          fi
        fi
      fi
    fi
  done
}

## Utility: safe_grep_dir <dir> <pattern>
## Guard grep usage to avoid noisy stderr when directory contains broken symlinks
safe_grep_dir() {
  local dir="$1" pattern="$2"
  if [[ ! -d "$dir" ]]; then
    return 0
  fi
  grep -R --line-number -- "$pattern" "$dir" 2>/dev/null || true
}

## PostgreSQL checks removed
# Historically this script validated connectivity to a PostgreSQL server.
# PostgreSQL is deprecated in this deployment (migrated to MariaDB + Chroma),
# so the legacy psql-based connectivity checks were intentionally removed to
# avoid requiring the `psql` client on the host. If you need database checks
# for MariaDB in the future, add a dedicated check that uses the mysql client
# or a small Python health probe.

run_reset_and_start() {
  local repo_root="$1"
  local reset_script="$repo_root/infrastructure/systemd/$RESET_SCRIPT_NAME"
  if [[ ! -x "$reset_script" ]]; then
    log_error "Reset script not executable at $reset_script"
    exit 1
  fi
  log_info "Invoking $RESET_SCRIPT_NAME to restart services"
  shift
  "$reset_script" "$@"
}

# Ensure systemd drop-ins for ordering/dependency gating are present
ensure_systemd_dropins() {
  local repo_root="$1"
  local dropins_created=false

  # Allow operators to opt-out if desired
  if [[ "${DISABLE_AUTOMATIC_SYSTEMD_DEPENDS:-false}" == "true" ]]; then
    log_warn "DISABLE_AUTOMATIC_SYSTEMD_DEPENDS set; skipping automatic unit drop-in creation"
    return 0
  fi

  declare -A deps=()
  # Map service -> space-separated dependencies (other instanced services)
  deps[synthesizer]="dashboard mcp_bus"
  deps[crawler]="crawl4ai mcp_bus"
  deps[crawler_control]="crawl4ai mcp_bus"

  for svc in "${!deps[@]}"; do
    local requires=()
    IFS=' ' read -r -a requires <<< "${deps[$svc]}"
    if [[ ${#requires[@]} -eq 0 ]]; then
      continue
    fi
    local dropin_dir="/etc/systemd/system/justnews@${svc}.service.d"
    local dropin_file="$dropin_dir/10-deps.conf"
    mkdir -p "$dropin_dir"
    local wants_line=""
    local after_line=""
    for r in "${requires[@]}"; do
      wants_line+="$(printf 'Wants=justnews@%s.service\n' "$r")"
      after_line+="$(printf 'After=justnews@%s.service\n' "$r")"
    done

    # Write to a temporary file first to avoid half-written confs
    local tmpfile
    tmpfile=$(mktemp)
    # Build the drop-in file atomically using a subshell to ensure per-line content
    (
      echo '[Unit]'
      for r in "${requires[@]}"; do
        echo "Wants=justnews@${r}.service"
      done
      for r in "${requires[@]}"; do
        echo "After=justnews@${r}.service"
      done
    ) > "$tmpfile"

    # Only overwrite if content changed to minimize daemon-reloads
    if [[ -f "$dropin_file" ]]; then
      if cmp -s "$tmpfile" "$dropin_file"; then
        rm -f "$tmpfile"
        continue
      fi
    fi
    mv "$tmpfile" "$dropin_file"
    chmod 644 "$dropin_file" || true
    log_info "Wrote systemd drop-in for justnews@${svc} to include: ${requires[*]}"
    dropins_created=true
  done

  if [[ "$dropins_created" == true ]]; then
    log_info "Reloading systemd to pick up new unit drop-ins"
    systemctl daemon-reload
  fi
}

run_health_summary() {
  local repo_root="$1"
  local health_script="$repo_root/infrastructure/systemd/$HEALTH_SCRIPT_NAME"
  if [[ -x "$health_script" ]]; then
    log_info "Running consolidated health check"
    if "$health_script"; then
      log_success "Health check completed"
    else
      log_warn "Health check reported issues"
    fi
  else
    log_warn "Health check script not found at $health_script"
  fi
}

start_monitoring_stack() {
  local repo_root="$1"
  local install_script="$repo_root/infrastructure/systemd/$MONITORING_INSTALL_RELATIVE_PATH"
  local prom_service="justnews-prometheus.service"
  local grafana_service="justnews-grafana.service"
  local node_service="justnews-node-exporter.service"
  local env_file="/etc/justnews/monitoring.env"
  local prom_bin=""
  local grafana_bin=""
  local node_bin=""

  if ! id -u justnews >/dev/null 2>&1; then
    log_warn "System user 'justnews' not present; skipping monitoring stack startup"
    return 0
  fi

  if [[ ! -x "$install_script" ]]; then
    log_warn "Monitoring install script not available at $install_script; skipping monitoring stack startup"
    return 0
  fi

  if [[ -r "$env_file" ]]; then
    # shellcheck disable=SC1090
    source "$env_file"
    prom_bin="${PROMETHEUS_BIN:-}"
    grafana_bin="${GRAFANA_BIN:-}"
    node_bin="${NODE_EXPORTER_BIN:-}"
  fi

  if systemctl is-active --quiet "$prom_service" \
     && systemctl is-active --quiet "$grafana_service" \
     && systemctl is-active --quiet "$node_service"; then
    log_info "Monitoring services already active; skipping reinstall"
    return 0
  fi

  local -a extra_args=(--enable --start)
  if [[ ! -r "$env_file" ]]; then
    log_warn "Monitoring environment file missing; installer will bootstrap binaries and defaults"
    extra_args+=(--install-binaries)
  fi

  local binaries_missing=false
  if [[ -z "$prom_bin" || ! -x "$prom_bin" ]]; then
    binaries_missing=true
  fi
  if [[ -z "$grafana_bin" || ! -x "$grafana_bin" ]]; then
    binaries_missing=true
  fi
  if [[ -z "$node_bin" || ! -x "$node_bin" ]]; then
    binaries_missing=true
  fi

  if [[ "$binaries_missing" == true ]]; then
    log_warn "Monitoring binaries missing; installer will fetch official releases"
    extra_args+=(--install-binaries)
  fi

  log_info "Provisioning monitoring stack via install_monitoring_stack.sh"
  if "$install_script" "${extra_args[@]}"; then
    local failures=()
    systemctl is-active --quiet "$node_service" || failures+=("$node_service")
    systemctl is-active --quiet "$prom_service" || failures+=("$prom_service")
    systemctl is-active --quiet "$grafana_service" || failures+=("$grafana_service")

    if [[ ${#failures[@]} -eq 0 ]]; then
      log_success "Monitoring stack running (node_exporter, Prometheus, Grafana)"
    else
      log_warn "Monitoring install completed but the following services are not active: ${failures[*]}"
    fi
  else
    log_error "Monitoring stack install script reported an error"
    return 1
  fi
}

stop_application_services() {
  local repo_root="$1"
  local enable_script="$repo_root/infrastructure/systemd/scripts/enable_all.sh"

  if [[ ! -x "$enable_script" ]]; then
    log_error "Service control script missing: $enable_script"
    exit 1
  fi

  log_info "Stopping JustNews application services"
  if "$enable_script" stop; then
    log_success "Application services stopped"
  else
    log_warn "enable_all.sh stop reported issues"
  fi

  log_info "Disabling JustNews application services"
  if "$enable_script" disable; then
    log_success "Application services disabled"
  else
    log_warn "enable_all.sh disable reported issues"
  fi
}

stop_monitoring_stack() {
  local services=(
    "justnews-grafana.service"
    "justnews-prometheus.service"
    "justnews-node-exporter.service"
  )
  local found_active=false

  for service in "${services[@]}"; do
    if systemctl list-unit-files "$service" >/dev/null 2>&1; then
      if systemctl is-active --quiet "$service"; then
        found_active=true
        log_info "Stopping $service"
        if systemctl stop "$service"; then
          log_success "$service stopped"
        else
          log_warn "Failed to stop $service"
        fi
      fi
    fi
  done

  if [[ "$found_active" == false ]]; then
    log_info "Monitoring services already stopped or not installed"
  fi
}

start_dev_telemetry_stack() {
  local repo_root="$1"
  # When ENABLE_DEV_TELEMETRY is not set to "true" we skip starting the
  # local development telemetry stack. This keeps the canonical startup
  # safe for production-like hosts while allowing developers to opt-in in
  # their /etc/justnews/global.env or other environment overrides.
  if [[ "${ENABLE_DEV_TELEMETRY:-false}" != "true" ]]; then
    log_info "ENABLE_DEV_TELEMETRY not set; skipping dev telemetry stack (docker compose)"
    return 0
  fi

  local compose_file="$repo_root/infrastructure/monitoring/dev-docker-compose.yaml"
  if [[ ! -f "$compose_file" ]]; then
    log_warn "Dev telemetry compose file not found: $compose_file; skipping"
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    log_warn "Docker not installed or not in PATH; cannot start dev telemetry stack"
    return 0
  fi

  # Choose compose invoker robustly: prefer `docker compose` plugin, fall back to `docker-compose` binary.
  local compose_invoker=""
  if docker compose version >/dev/null 2>&1; then
    compose_invoker="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    compose_invoker="docker-compose"
  fi

  if [[ -z "$compose_invoker" ]]; then
    log_warn "No docker compose invoker found (neither 'docker compose' nor 'docker-compose' is available); skipping dev telemetry stack"
    return 0
  fi

  local compose_dir; compose_dir="$(dirname "$compose_file")"
  local compose_base; compose_base="$(basename "$compose_file")"

  # Quick port conflict check - developer hosts may already have OTLP/collector
  # listening on the standard ports. If there is a conflict we skip starting
  # the dev telemetry stack unless explicitly forced with
  # ENABLE_DEV_TELEMETRY_FORCE=1 (safe default to avoid bind failures).
  # Determine the host ports that the dev compose will use. These honour
  # environment variables (so operators can override) and default to safe
  # alternate dev ports which avoid colliding with a running host OTEL.
  local LOKI_PORT_HOST="${LOKI_PORT:-13100}"
  local TEMPO_HTTP_PORT_HOST="${TEMPO_HTTP_PORT:-24268}"
  local TEMPO_JAEGER_PORT_HOST="${TEMPO_JAEGER_PORT:-19411}"
  local OTEL_GRPC_PORT_HOST="${OTEL_GRPC_PORT:-24317}"
  local OTEL_HTTP_PORT_HOST="${OTEL_HTTP_PORT:-24318}"
  local NODE_METRICS_PORT_HOST="${NODE_METRICS_PORT:-18889}"
  local DEMO_PORT_HOST="${DEMO_PORT:-18080}"

  local compose_ports=($LOKI_PORT_HOST $TEMPO_HTTP_PORT_HOST $TEMPO_JAEGER_PORT_HOST $OTEL_GRPC_PORT_HOST $OTEL_HTTP_PORT_HOST $NODE_METRICS_PORT_HOST $DEMO_PORT_HOST)
  local conflict_found=0
  if [[ "${ENABLE_DEV_TELEMETRY_FORCE:-0}" != "1" ]]; then
    for p in "${compose_ports[@]}"; do
      if ss -ltn | awk '{print $4}' | grep -E ":$p$" >/dev/null 2>&1; then
        log_warn "Dev telemetry port $p already in use on host - skipping dev telemetry startup; set ENABLE_DEV_TELEMETRY_FORCE=1 to override"
        conflict_found=1
      fi
    done
    if [[ $conflict_found -ne 0 ]]; then
      return 0
    fi
  else
    log_info "ENABLE_DEV_TELEMETRY_FORCE=1: forcing dev telemetry startup despite potential port conflicts"
  fi

  log_info "Bringing up dev telemetry stack via $compose_invoker (cwd=$compose_dir): $compose_base"
  if (cd "$compose_dir" && $compose_invoker -f "$compose_base" up -d); then
    log_success "Dev telemetry stack started (docker compose)"
  else
    # Try fallback if the preferred invoker exists but fails.
    log_warn "Primary compose invoker ($compose_invoker) failed; attempting fallback"
    if [[ "$compose_invoker" == "docker compose" ]] && command -v docker-compose >/dev/null 2>&1; then
      log_info "Attempting fallback: docker-compose -f $compose_base up -d (cwd=$compose_dir)"
      if (cd "$compose_dir" && docker-compose -f "$compose_base" up -d); then
        log_success "Dev telemetry stack started (docker-compose fallback)"
      else
        log_warn "Failed to start dev telemetry stack with docker-compose fallback"
      fi
    else
      log_warn "Failed to start dev telemetry stack with $compose_invoker"
    fi
  fi
}

stop_dev_telemetry_stack() {
  local repo_root="$1"

  # Always attempt to tear down any *JustNews-managed* dev telemetry artefacts
  # (systemd unit or docker compose project) even when ENABLE_DEV_TELEMETRY is
  # not set. This addresses the case where a previously started dev telemetry
  # instance is left running and causes port conflicts when attempting to
  # start the stack again.

  # 1) Prefer to stop the systemd-managed unit if present
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl --no-pager is-active --quiet justnews-dev-telemetry.service; then
      log_info "Stopping systemd unit justnews-dev-telemetry.service"
      if systemctl stop justnews-dev-telemetry.service; then
        log_success "Stopped justnews-dev-telemetry.service"
      else
        log_warn "Failed to stop justnews-dev-telemetry.service via systemctl"
      fi
      # If unit was active we consider the teardown complete (containers will be removed by the unit)
      return 0
    fi
  fi

  # 2) If the unit was not active, attempt to find and tear down docker-compose
  local compose_file="$repo_root/infrastructure/monitoring/dev-docker-compose.yaml"
  if [[ ! -f "$compose_file" ]]; then
    log_info "No dev telemetry compose file found at $compose_file; nothing to stop"
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    log_info "Docker not found; no dev telemetry containers to stop"
    return 0
  fi

  # If any container related to the dev telemetry project exists, bring it down
  # Use a conservative name search to avoid impacting unrelated containers.
  local found=0
  local known_containers=(justnews-loki justnews-tempo justnews-otel-node justnews-demo-emitter)
  for c in "${known_containers[@]}"; do
    if docker ps -a --filter "name=$c" --format '{{.Names}}' | grep -xq "$c"; then
      found=1
      break
    fi
  done

  if [[ $found -eq 0 ]]; then
    log_info "No JustNews dev telemetry containers found; nothing to stop"
    return 0
  fi

  # Choose compose invoker and run down from the compose dir so relative mounts resolve
  local compose_invoker=""
  if docker compose version >/dev/null 2>&1; then
    compose_invoker="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    compose_invoker="docker-compose"
  fi

  local compose_dir; compose_dir="$(dirname "$compose_file")"
  local compose_base; compose_base="$(basename "$compose_file")"

  if [[ -n "$compose_invoker" ]]; then
    log_info "Tearing down dev telemetry containers via $compose_invoker (cwd=$compose_dir)"
    if (cd "$compose_dir" && $compose_invoker -f "$compose_base" down); then
      log_success "Dev telemetry stack stopped (compose)"
      return 0
    else
      log_warn "Failed to stop dev telemetry stack via $compose_invoker"
    fi
  fi

  # As a last resort attempt docker-compose binary
  if command -v docker-compose >/dev/null 2>&1; then
    log_info "Attempting docker-compose down as fallback (cwd=$compose_dir)"
    if (cd "$compose_dir" && docker-compose -f "$compose_base" down); then
      log_success "Dev telemetry stack stopped (docker-compose)"
      return 0
    else
      log_warn "docker-compose fallback failed to stop dev telemetry stack"
    fi
  fi

  log_warn "Unable to tear down dev telemetry stack: manual cleanup may be required (check docker ps -a)"
}

start_gui_monitor() {
  local repo_path="$1"
  # Only start if we are in a sudo environment with a real user and a display
  if [[ -n "${SUDO_USER:-}" && -n "${DISPLAY:-}" ]]; then
     log_info "Starting GUI Monitor for user $SUDO_USER on display $DISPLAY..."
     
     # Resolve the python executable used by the environment
     # We can try to use the one from global.env or just rely on 'python' in the path 
     # if we were running as the user, but we are root here.
     # The repo functions usually set up PYTHONPATH.
     
     local monitor_script="$repo_path/GUI_monitor.py"
     if [[ ! -f "$monitor_script" ]]; then
       log_warn "GUI_monitor.py not found at $monitor_script; skipping."
       return 0
     fi
     
     # We need to run this as the user.
     # We use nohup and background checking to ensure it survives the script exit
     # and doesn't block.
     
     local python_cmd="${PYTHON_BIN:-python3}"
     
     # Check if custom conda env is needed?
    # The user may be running with $HOME/miniconda3/envs/${CANONICAL_ENV}/bin/python3
     # We should try to use that if possible.
     
     if [[ -n "${CONDA_ENV:-}" ]]; then
        # If we know the conda env, we can try to find its python
        # But for simplicity, let's trust PYTHON_BIN if set, or just run whatever 'python' maps to for the user?
        # Actually, running 'python' as user might pick up system python.
        # PYTHON_BIN in this script comes from global.env which is correct.
        true
     fi
     
     # Run as user
     sudo -u "$SUDO_USER" DISPLAY="$DISPLAY" XAUTHORITY="${XAUTHORITY:-/home/$SUDO_USER/.Xauthority}" \
       nohup "$python_cmd" "$monitor_script" >/dev/null 2>&1 &
       
     log_success "GUI Monitor started."
  fi
}

stop_gui_monitor() {
  if [[ -n "${SUDO_USER:-}" ]]; then
    # We only want to kill the monitor started by this user
    if pgrep -u "$SUDO_USER" -f "GUI_monitor.py" > /dev/null; then
      log_info "Stopping GUI Monitor..."
      pkill -u "$SUDO_USER" -f "GUI_monitor.py" || true
      log_success "GUI Monitor stopped."
    fi
  fi
}

main() {
  parse_args "$@"
  if [[ "$SHOW_USAGE" == true ]]; then
    usage
    exit 0
  fi

  require_root
  require_command systemctl

  # Resolve the repository root early — several checks below need an absolute
  # repo_root path (e.g. scripts invoked later in the flow). Previously the
  # variable was assigned too late and some checks attempted to reference
  # "$repo_root" before it existed which would lead to incorrect behaviour.
  local repo_root
  repo_root="$(resolve_repo_root)"

  if [[ "$REQUEST_STOP" == true ]]; then
    if [[ "$DRY_RUN" == true ]]; then
      log_info "Dry-run requested; skipping service shutdown"
      log_success "Prerequisite checks completed (dry run)"
    else
      stop_application_services "$repo_root"
      # Ensure dev telemetry is torn down first (if enabled) before stopping
      # the systemd monitoring stack to avoid orphaned compose containers.
      stop_dev_telemetry_stack "$repo_root"
      stop_monitoring_stack
      stop_gui_monitor
      log_success "Canonical system shutdown completed"
    fi
    return 0
  fi

  require_command mountpoint
  require_command mount
  load_environment
  # Ensure a PYTHON_BIN is present in the system global env so downstream
  # scripts, systemd and service templates consistently have a runtime set.
  if [[ -x "$repo_root/infrastructure/systemd/scripts/ensure_global_python_bin.sh" ]]; then
    # Prefer using system /etc/justnews/global.env unless caller passed a different one
    sudo bash "$repo_root/infrastructure/systemd/scripts/ensure_global_python_bin.sh" || true
  fi
  ensure_env_value SERVICE_DIR
  ensure_env_value PYTHON_BIN
  check_python_runtime
  # Ensure protobuf version meets minimum requirements to avoid deprecated C-API usage
  # CI and dry-run callers can opt out by setting SKIP_PROTOBUF_CHECK=true
  if [[ "${SKIP_PROTOBUF_CHECK:-false}" == "true" ]]; then
    log_warn "SKIP_PROTOBUF_CHECK=true — skipping protobuf version check"
  else
    if ! run_python_script "$repo_root/scripts/checks/check_protobuf_version.py"; then
      log_error "Protobuf version does not meet the recommended minimum; please upgrade your Python environment's protobuf to >=4.24.0. Aborting startup."
      exit 1
    fi
  fi
  check_data_mount
  
  # Ensure local databases are running before we probe them
  ensure_local_databases

  # MariaDB check: skip when MARIADB_HOST unset or SKIP_MARIADB_CHECK=true
  check_mariadb_connectivity
  # Database connectivity checks are intentionally skipped here (PostgreSQL deprecated)

  # repo_root was resolved earlier; do not re-declare / reassign here.

  # Gather args destined for reset_and_start while keeping a copy for health logic
  if [[ "$DRY_RUN" == true ]]; then
    log_info "Dry-run requested; skipping service restart"
  else
    # Ensure systemd unit drop-ins for known agent dependencies
    ensure_systemd_dropins "$repo_root"

    # Safety: if this appears to be an interactive desktop session (DISPLAY/XDG set)
    # and the developer opted into dev telemetry, we proactively enable SAFE_MODE
    # unless the caller explicitly provided a --safe-mode argument OR the user has
    # explicitly set SAFE_MODE=false in global.env. This prevents accidental
    # GPU-heavy work (model loading / OOMs) which can crash desktop processes such
    # as VS Code, while still respecting explicit user configuration.
    if [[ -n "${DISPLAY:-}" || -n "${XDG_SESSION_TYPE:-}" ]] && [[ "${ENABLE_DEV_TELEMETRY:-false}" == "true" ]]; then
      # check if --safe-mode already provided in forwarded args
      safe_mode_present=false
      for a in "${FORWARDED_ARGS[@]}"; do
        if [[ "$a" == "--safe-mode" ]]; then
          safe_mode_present=true
          break
        fi
      done

      if [[ "$safe_mode_present" == false ]]; then
        # Check if user has explicitly disabled SAFE_MODE in global.env
        current_safe_mode="${SAFE_MODE:-}"
        if [[ "$current_safe_mode" == "false" ]]; then
          log_info "Interactive desktop detected but SAFE_MODE=false in global.env; respecting user configuration (GPU usage enabled)"
        else
          log_info "Interactive desktop detected + ENABLE_DEV_TELEMETRY=true; adding --safe-mode on to startup to avoid GPU usage"
          FORWARDED_ARGS+=("--safe-mode" "on")
        fi
      else
        log_info "--safe-mode already present in args; leaving unchanged"
      fi
    fi
    run_reset_and_start "$repo_root" "${FORWARDED_ARGS[@]}"
    if ! start_monitoring_stack "$repo_root"; then
      exit 1
    fi
    # Optionally start the local development telemetry stack if enabled.
    start_dev_telemetry_stack "$repo_root"
    # The Crawl4AI bridge is managed as a regular justnews@ service named
    # 'crawl4ai' and will be enabled/started by the reset_and_start ->
    # enable_all.sh flow. No dedicated enable/start is required here.
    log_info "Crawl4AI bridge will be started by enable_all.sh as justnews@crawl4ai"
    run_health_summary "$repo_root"
    start_gui_monitor "$repo_root"
  fi

  # ----------------------------
  # Chroma canonical enforcement
  # ----------------------------
  chroma_require_canonical="${CHROMADB_REQUIRE_CANONICAL:-1}"
  chroma_canonical_host="${CHROMADB_CANONICAL_HOST:-}"
  chroma_canonical_port="${CHROMADB_CANONICAL_PORT:-}"
  chroma_host="${CHROMADB_HOST:-}"
  chroma_port="${CHROMADB_PORT:-}"

  if [[ "$chroma_require_canonical" == "1" ]]; then
    if [[ -z "$chroma_canonical_host" || -z "$chroma_canonical_port" ]]; then
      log_error "CHROMADB_REQUIRE_CANONICAL is enabled but CHROMADB_CANONICAL_HOST/PORT are not set; aborting startup."
      exit 1
    fi
    if [[ -z "$chroma_host" || -z "$chroma_port" ]]; then
      log_error "CHROMADB_HOST/PORT must be set in the environment (or global.env) to connect to ChromaDB."
      exit 1
    fi
    if [[ "$chroma_host" != "$chroma_canonical_host" || "$chroma_port" != "$chroma_canonical_port" ]]; then
      log_error "CHROMADB_HOST/PORT in environment $chroma_host:$chroma_port does not match canonical $chroma_canonical_host:$chroma_canonical_port; aborting startup."
      log_info "Helpful steps:"
      log_info "  1) Use $ROOT/scripts/chroma_diagnose.py to discover endpoints and root info"
      log_info "     - Example: PYTHONPATH=. conda run -n ${CONDA_ENV:-$DEFAULT_CONDA_ENV} python scripts/chroma_diagnose.py --host $chroma_host --port $chroma_port"
      log_info "  2) If tenant/collection missing, run the bootstrap helper: scripts/chroma_bootstrap.py"
      log_info "     - Example: PYTHONPATH=. conda run -n ${CONDA_ENV:-$DEFAULT_CONDA_ENV} python scripts/chroma_bootstrap.py --host $chroma_canonical_host --port $chroma_canonical_port --tenant default_tenant --collection articles"
      exit 1
    fi
    # Run a diagnostic to confirm the canonical host/port is a Chroma instance
    # Prefer a simple HTTP probe (modern Chroma exposes /api/v2/auth/identity),
    # fall back to /api/v1/health or root. Only invoke the Python-based
    # scripts/chroma_diagnose.py helper if HTTP probes fail (some local
    # environments may have incompatible native libs and that tool can crash
    # the runtime — prefer lightweight HTTP checks first).
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS "http://${chroma_host}:${chroma_port}/api/v2/auth/identity" >/dev/null 2>&1; then
        log_info "Chroma identity endpoint OK: ${chroma_host}:${chroma_port}"
      elif curl -fsS "http://${chroma_host}:${chroma_port}/api/v1/health" >/dev/null 2>&1 || curl -fsS "http://${chroma_host}:${chroma_port}/" >/dev/null 2>&1; then
        log_info "Chroma reachable via alternate endpoint: ${chroma_host}:${chroma_port}"
      else
        log_warn "HTTP probes failed for Chroma at ${chroma_host}:${chroma_port}; falling back to Python diagnostic helper"
        if ! run_python_script "$repo_root/scripts/chroma_diagnose.py" --host "$chroma_host" --port "$chroma_port"; then
          log_error "Chroma diagnostic failed for $chroma_host:$chroma_port (fatal under CHROMADB_REQUIRE_CANONICAL)"
          exit 1
        fi
      fi
    else
      # No curl available, try the Python helper as a last resort
      if ! run_python_script "$repo_root/scripts/chroma_diagnose.py" --host "$chroma_host" --port "$chroma_port"; then
        log_error "Chroma diagnostic failed for $chroma_host:$chroma_port (fatal under CHROMADB_REQUIRE_CANONICAL)"
        exit 1
      fi
    fi
    log_info "Chroma canonical host/port validated: $chroma_host:$chroma_port"
  else
    log_warn "CHROMADB_REQUIRE_CANONICAL not enabled; starting without strict Chroma enforcement"
  fi

  if [[ "$DRY_RUN" == true ]]; then
    log_success "Prerequisite checks completed (dry run)"
  else
    log_success "Canonical system startup completed"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
