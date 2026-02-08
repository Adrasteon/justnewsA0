#!/usr/bin/env bash
set -euo pipefail

# check_db_services.sh
# Conservative diagnostic helper that inspects systemd/machine state for
# MariaDB and ChromaDB and probes connectivity using values from
# /etc/justnews/global.env (or the repo-level global.env when that file is
# not present on the system). This is read-only and non-destructive.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GLOBAL_ENV=${GLOBAL_ENV:-/etc/justnews/global.env}

warn() { echo -e "[WARN] $*"; }
info() { echo -e "[INFO] $*"; }
ok() { echo -e "[OK] $*"; }
fail() { echo -e "[FAIL] $*"; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [--env /path/to/global.env]

Performs non-destructive checks for MariaDB and ChromaDB on the host:
  - verifies systemd unit existence and 'enabled'/'active' state
  - tails recent journal logs for each service (N lines)
  - probes connectivity using configured host/port/user/password from env
  - suggests remediation steps when failures are found

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) GLOBAL_ENV="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -f "$GLOBAL_ENV" ]]; then
  info "Loading environment file: $GLOBAL_ENV"
  # shellcheck disable=SC1090
  set -a; source "$GLOBAL_ENV"; set +a
else
  warn "Environment file not found at $GLOBAL_ENV; some checks may be skipped"
fi

JOURNAL_LINES=75

check_systemd_unit() {
  local unit=$1
  info "Checking systemd unit: $unit"
  if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
    systemctl is-enabled --quiet "$unit" && ok "$unit enabled" || warn "$unit not enabled"
    systemctl is-active --quiet "$unit" && ok "$unit active" || warn "$unit inactive/failed"
    echo "--- last journal entries for $unit (tail $JOURNAL_LINES lines) ---"
    sudo journalctl -u "$unit" -n $JOURNAL_LINES --no-pager || true
  else
    warn "$unit unit file not present on host"
  fi
  echo
}

probe_mariadb() {
  # Guard if MARIADB_HOST unset: nothing to probe
  if [[ -z "${MARIADB_HOST:-}" ]]; then
    warn "MARIADB_HOST not set; skipping MariaDB probe"
    return
  fi
  local host=${MARIADB_HOST:-127.0.0.1}
  local port=${MARIADB_PORT:-3306}
  local user=${MARIADB_USER:-justnews}
  local pass=${MARIADB_PASSWORD:-}
  local db=${MARIADB_DB:-justnews}

  info "Probing MariaDB at ${host}:${port} (user=${user}, db=${db})"

  # Prefer mysql client if present
  if command -v mysql >/dev/null 2>&1; then
    # Avoid printing password in shell history; build arguments safely
    local args=( -h "$host" -P "$port" -u "$user" )
    if [[ -n "$pass" ]]; then
      args+=( -p"$pass" )
    fi
    args+=( -e "SELECT 1;" "$db" )

    if timeout 5 mysql "${args[@]}" >/dev/null 2>&1; then
      ok "MariaDB reachable with mysql client"
    else
      fail "MariaDB probe failed with mysql client. Check: service active, host/port, credentials in $GLOBAL_ENV"
    fi
    return
  fi

  # Fallback: python pymysql probe
  if [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
    info "mysql-client not found; attempting python (pymysql) probe using PYTHON_BIN=$PYTHON_BIN"
    if "$PYTHON_BIN" - <<PY >/dev/null 2>&1
import sys
try:
    import pymysql
except Exception as e:
    print('no-pymysql:'+str(e))
    sys.exit(2)
try:
    conn = pymysql.connect(host='${host}', port=${port}, user='${user}', password='${pass}', database='${db}', connect_timeout=5)
    cur = conn.cursor(); cur.execute('SELECT 1'); conn.close()
    sys.exit(0)
except Exception as e:
    print('err:'+str(e))
    sys.exit(3)
PY
    then
      ok "MariaDB reachable via python+pymysql"
    else
      fail "MariaDB python probe failed (pymysql missing or connection refused)." 
    fi
    return
  fi

  warn "No mysql client or usable PYTHON_BIN+pymysql detected; cannot perform MariaDB connectivity probe. Install mysql-client or ensure PYTHON_BIN points to Python with pymysql installed."
}

probe_chroma() {
  if [[ -z "${CHROMADB_HOST:-}" || -z "${CHROMADB_PORT:-}" ]]; then
    warn "CHROMADB_HOST/CHROMADB_PORT not set; skipping Chroma probe"
    return
  fi
  local host=${CHROMADB_HOST}
  local port=${CHROMADB_PORT}
  info "Probing Chroma at ${host}:${port}"

  if command -v curl >/dev/null 2>&1; then
    # Prefer the identity endpoint on modern Chroma versions which returns 200.
    if curl -fsS "http://${host}:${port}/api/v2/auth/identity" >/dev/null 2>&1; then
      ok "Chroma identity endpoint OK"
    elif curl -fsS "http://${host}:${port}/api/v1/health" >/dev/null 2>&1 || curl -fsS "http://${host}:${port}/api/v1/heartbeat" >/dev/null 2>&1 || curl -fsS "http://${host}:${port}/" >/dev/null 2>&1; then
      ok "Chroma reachable (alternate endpoint)"
    else
      fail "Chroma probe failed (no response or non-200). Check if chromadb.service is running or that CHROMADB_HOST/PORT match a running instance."
    fi
    return
  fi

  # Fallback to python chroma_diagnose if available in repo
  if [[ -f "$ROOT_DIR/scripts/chroma_diagnose.py" ]]; then
    info "curl missing; attempting repo diagnose helper via PYTHON_BIN"
    if [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
      if PYTHONPATH=$ROOT_DIR "$PYTHON_BIN" "$ROOT_DIR/scripts/chroma_diagnose.py" --host "$host" --port "$port"; then
        ok "Chroma diagnostic passed (via scripts/chroma_diagnose.py)"
      else
        fail "Chroma diagnostic script reported a problem"
      fi
      return
    fi
  fi

  warn "Unable to probe Chroma (missing curl and no usable python diagnose helper)"
}

echo "==== JustNews DB service diagnostic helper ===="
echo

info "Repository root: $ROOT_DIR"
info "Global env:     $GLOBAL_ENV"
echo

echo "== MariaDB system/service checks =="
check_systemd_unit mariadb
probe_mariadb
echo

echo "== ChromaDB system/service checks =="
check_systemd_unit chromadb
probe_chroma
echo

echo "Diagnostics complete. Suggested next steps:"
echo " - If a service is inactive/failed: inspect journalctl -u <service> and re-run the setup helper: infrastructure/systemd/complete_mariadb.sh"
echo " - If connectivity fails: verify /etc/justnews/global.env host/port/user/password match the service and update or recreate users accordingly"
echo " - For Chroma: ensure CHROMADB_REQUIRE_CANONICAL/CHROMADB_CANONICAL_HOST/PORT match your environment if strict canonical enforcement is enabled"

exit 0
