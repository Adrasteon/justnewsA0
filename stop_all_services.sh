#!/usr/bin/env bash
#
# stop_all_services.sh - Canonical comprehensive service shutdown script
#
# Gracefully stops all running agents and database services in reverse order.
#
# Usage:
#   ./stop_all_services.sh [--help] [--force] [--skip-db]
#
# Environment:
#   VERBOSE=1         - Show verbose output
#   FORCE=1          - Force kill services without graceful shutdown
#   SKIP_DB=1        - Don't stop database services
#

set -euo pipefail

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

# Source the agents manifest
AGENTS_MANIFEST_FILE="${PROJECT_ROOT}/infrastructure/agents_manifest.sh"
if [ -f "${AGENTS_MANIFEST_FILE}" ]; then
  # shellcheck disable=SC1090
  source "${AGENTS_MANIFEST_FILE}"
else
  echo "ERROR: agents_manifest.sh not found at ${AGENTS_MANIFEST_FILE}" >&2
  exit 1
fi

# Feature flags
FORCE="${FORCE:-0}"
SKIP_DB="${SKIP_DB:-0}"
VERBOSE="${VERBOSE:-0}"
GRACEFUL_TIMEOUT="${GRACEFUL_TIMEOUT:-10}"
KILL_TIMEOUT="${KILL_TIMEOUT:-3}"

# Service endpoints
MARIADB_PORT="${MARIADB_PORT:-3306}"
CHROMADB_PORT="${CHROMADB_PORT:-3307}"
REDIS_PORT="${REDIS_PORT:-6379}"

# ============================================================================
# LOGGING & OUTPUT
# ============================================================================

timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

log_info() {
  printf "%s \033[0;34m[INFO]\033[0m %s\n" "$(timestamp)" "$*"
}

log_success() {
  printf "%s \033[0;32m[SUCCESS]\033[0m %s\n" "$(timestamp)" "$*"
}

log_warn() {
  printf "%s \033[1;33m[WARN]\033[0m %s\n" "$(timestamp)" "$*" >&2
}

log_error() {
  printf "%s \033[0;31m[ERROR]\033[0m %s\n" "$(timestamp)" "$*" >&2
}

log_verbose() {
  if [ "${VERBOSE}" = "1" ]; then
    printf "%s \033[0;36m[DEBUG]\033[0m %s\n" "$(timestamp)" "$*"
  fi
}

log_section() {
  printf "\n%s \033[1;36m=== %s ===\033[0m\n" "$(timestamp)" "$*"
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

show_help() {
  cat <<'EOF'
stop_all_services.sh - Canonical JustNews service shutdown

USAGE:
  ./stop_all_services.sh [OPTIONS]

OPTIONS:
  --help              Show this help message
  --force             Force kill services without graceful shutdown
  --skip-db           Skip database service shutdown

EXAMPLES:
  # Graceful shutdown of all services
  ./stop_all_services.sh

  # Force shutdown (immediate kills)
  ./stop_all_services.sh --force

  # Stop only agents (keep databases running)
  ./stop_all_services.sh --skip-db

ENVIRONMENT VARIABLES:
  VERBOSE=1           Show verbose logging
  FORCE=1            Force kill instead of graceful
  SKIP_DB=1          Skip database shutdown
  GRACEFUL_TIMEOUT=10 Timeout for graceful shutdown (seconds)
  KILL_TIMEOUT=3     Timeout for kill signal (seconds)

EOF
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --help)
        show_help
        exit 0
        ;;
      --force)
        FORCE=1
        shift
        ;;
      --skip-db)
        SKIP_DB=1
        shift
        ;;
      *)
        log_error "Unknown option: $1"
        show_help
        exit 1
        ;;
    esac
  done
}

get_listening_ports() {
  # Get all listening ports on localhost
  if command -v ss &>/dev/null; then
    ss -ltn 2>/dev/null | grep -oP '(?<=:)\d+(?=\s)' | sort -u
  elif command -v netstat &>/dev/null; then
    netstat -ltn 2>/dev/null | grep -oP '(?<=:)\d+(?=\s)' | sort -u
  else
    return 1
  fi
}

get_pids_for_port() {
  local port=$1

  if command -v lsof &>/dev/null; then
    lsof -ti "tcp:${port}" 2>/dev/null || true
  elif command -v ss &>/dev/null; then
    ss -ltnp 2>/dev/null | grep ":${port}" | sed -n 's/.*pid=\([0-9]*\).*/\1/p' || true
  else
    return 1
  fi
}

stop_agent() {
  local agent_name="$1"
  local port="$2"

  # Check if port is listening
  if ! ss -ltn "sport = :${port}" 2>/dev/null | grep -q LISTEN; then
    log_verbose "${agent_name} (port ${port}) not listening"
    return 0
  fi

  log_info "Stopping ${agent_name} on port ${port}..."

  # Try graceful shutdown first
  if [ "${FORCE}" != "1" ]; then
    log_verbose "Attempting graceful shutdown via /shutdown endpoint..."

    if command -v curl >/dev/null 2>&1; then
      local http_code
      http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        --max-time 3 "http://127.0.0.1:${port}/shutdown" 2>/dev/null || echo "000")

      if [ "${http_code}" = "200" ] || [ "${http_code}" = "202" ] || [ "${http_code}" = "204" ]; then
        log_verbose "Shutdown signal accepted (HTTP ${http_code}), waiting for port to close..."

        local waited=0
        while ss -ltn "sport = :${port}" 2>/dev/null | grep -q LISTEN && [ ${waited} -lt ${GRACEFUL_TIMEOUT} ]; do
          sleep 1
          waited=$((waited + 1))
        done

        if ! ss -ltn "sport = :${port}" 2>/dev/null | grep -q LISTEN; then
          log_success "${agent_name} stopped gracefully"
          return 0
        else
          log_warn "Port ${port} still listening after graceful timeout, will force kill"
        fi
      else
        log_verbose "Graceful shutdown endpoint not available (HTTP ${http_code})"
      fi
    fi
  fi

  # Force kill
  local pids
  pids=$(get_pids_for_port "${port}") || true

  if [ -zm "${pids}" ]; then
    # Try to find processes by module/agent name
    pids=$(pgrep -f "agents\\.${agent_name}" || true)
  fi

  if [ -n "${pids}" ]; then
    log_info "Force killing processes on port ${port}: ${pids}"

    for pid in ${pids}; do
      kill -TERM "${pid}" 2>/dev/null || true
    done

    sleep "${KILL_TIMEOUT}"

    for pid in ${pids}; do
      if kill -0 "${pid}" 2>/dev/null; then
        log_verbose "Sending SIGKILL to PID ${pid}"
        kill -9 "${pid}" 2>/dev/null || true
      fi
    done

    log_success "${agent_name} terminated"
  else
    log_warn "Could not find process for ${agent_name} on port ${port}"
  fi

  return 0
}

stop_all_agents() {
  log_section "Stopping All Agents"

  # Process agents in reverse order (reverse of start order)
  local agents=()
  local entry

  for entry in "${AGENTS_MANIFEST[@]}"; do
    IFS='|' read -r name _ port <<< "$entry"
    agents+=("${name}|${port}")
  done

  # Reverse array
  local reversed=()
  for ((i=${#agents[@]}-1; i>=0; i--)); do
    reversed+=("${agents[i]}")
  done

  # Stop each agent
  for entry in "${reversed[@]}"; do
    IFS='|' read -r name port <<< "$entry"
    stop_agent "${name}" "${port}"
  done

  log_section "All Agents Stopped"
}

stop_mariadb() {
  log_info "Stopping MariaDB on port ${MARIADB_PORT}..."

  if command -v systemctl &>/dev/null; then
    systemctl is-active --quiet mariadb || systemctl is-active --quiet mysql || {
      log_verbose "MariaDB not active via systemctl"
      return 0
    }

    if sudo systemctl stop mariadb 2>/dev/null || sudo systemctl stop mysql 2>/dev/null; then
      log_success "MariaDB stopped"
      return 0
    else
      log_warn "Could not stop MariaDB via systemctl"
    fi
  fi

  # Try to kill by port
  local pids
  pids=$(get_pids_for_port "${MARIADB_PORT}") || true

  if [ -n "${pids}" ]; then
    log_verbose "Killing MariaDB processes: ${pids}"
    for pid in ${pids}; do
      kill -TERM "${pid}" 2>/dev/null || true
    done
    sleep 2
    for pid in ${pids}; do
      kill -9 "${pid}" 2>/dev/null || true
    done
    log_success "MariaDB terminated"
  else
    log_verbose "MariaDB not running"
  fi
}

stop_chromadb() {
  log_info "Stopping ChromaDB on port ${CHROMADB_PORT}..."

  local pids
  pids=$(get_pids_for_port "${CHROMADB_PORT}") || true

  if [ -n "${pids}" ]; then
    log_verbose "Killing ChromaDB processes: ${pids}"
    for pid in ${pids}; do
      kill -TERM "${pid}" 2>/dev/null || true
    done
    sleep 2
    for pid in ${pids}; do
      kill -9 "${pid}" 2>/dev/null || true
    done
    log_success "ChromaDB terminated"
  else
    log_verbose "ChromaDB not running"
  fi
}

stop_redis() {
  log_info "Stopping Redis on port ${REDIS_PORT}..."

  if command -v redis-cli &>/dev/null; then
    if redis-cli -p "${REDIS_PORT}" shutdown 2>/dev/null; then
      log_success "Redis stopped gracefully"
      return 0
    fi
  fi

  # Force kill
  local pids
  pids=$(get_pids_for_port "${REDIS_PORT}") || true

  if [ -n "${pids}" ]; then
    log_verbose "Killing Redis processes: ${pids}"
    for pid in ${pids}; do
      kill -TERM "${pid}" 2>/dev/null || true
    done
    sleep 2
    for pid in ${pids}; do
      kill -9 "${pid}" 2>/dev/null || true
    done
    log_success "Redis terminated"
  else
    log_verbose "Redis not running"
  fi
}

stop_database_services() {
  if [ "${SKIP_DB}" = "1" ]; then
    log_section "Skipping Database Services (--skip-db)"
    return 0
  fi

  log_section "Stopping Database Services"

  # Stop in reverse order: MariaDB, ChromaDB, Redis
  stop_mariadb || true
  stop_chromadb || true
  stop_redis || true

  log_section "Database Services Stopped"
}

# ============================================================================
# MAIN
# ============================================================================

main() {
  log_info "JustNews Service Shutdown Script"
  log_info "Repository: ${PROJECT_ROOT}"
  echo

  # Parse command line arguments
  parse_args "$@"

  if [ "${FORCE}" = "1" ]; then
    log_warn "FORCE mode enabled - will skip graceful shutdown attempts"
  fi

  # Stop agents first (in reverse order)
  stop_all_agents || true

  # Stop database services
  stop_database_services || true

  log_section "Shutdown Complete"
  log_success "All services have been stopped"

  return 0
}

# Execute main function if not sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
