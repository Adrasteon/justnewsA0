#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/global.env"
PIDFILE="/tmp/justnews_services_logs/memory_governor/justnews_memory_governor.pid"
LOGFILE="/tmp/justnews_services_logs/memory_governor/justnews_memory_governor.log"
STATEFILE="/tmp/justnews_services_logs/memory_governor/justnews_memory_governor_state.json"
MAPFILE="/tmp/justnews_services_logs/memory_governor/managed_processes.json"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found"
  exit 1
fi

mkdir -p "$(dirname "${PIDFILE}")"

upsert_env() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    printf "\n%s=%s\n" "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

resolve_python() {
  if [[ -x "/deps/.venv/bin/python" ]]; then
    echo "/deps/.venv/bin/python"
    return 0
  fi
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    echo "${ROOT_DIR}/.venv/bin/python"
    return 0
  fi
  command -v python3
}

pid_for_port() {
  local port="$1"
  ss -ltnp 2>/dev/null | awk -v p=":${port}" '
    index($0, p) && /pid=/ {
      match($0, /pid=[0-9]+/)
      if (RSTART > 0) {
        print substr($0, RSTART + 4, RLENGTH - 4)
        exit
      }
    }
  '
}

# Persist enable flag + conservative defaults if unset
upsert_env "JUSTNEWS_MEMORY_GOVERNOR_ENABLED" "1"
upsert_env "JUSTNEWS_MEMORY_SOFT_PERCENT" "${JUSTNEWS_MEMORY_SOFT_PERCENT:-80}"
upsert_env "JUSTNEWS_MEMORY_HARD_PERCENT" "${JUSTNEWS_MEMORY_HARD_PERCENT:-84}"
upsert_env "JUSTNEWS_MEMORY_EMERGENCY_PERCENT" "${JUSTNEWS_MEMORY_EMERGENCY_PERCENT:-88}"
upsert_env "JUSTNEWS_MEMORY_RESUME_PERCENT" "${JUSTNEWS_MEMORY_RESUME_PERCENT:-75}"
upsert_env "JUSTNEWS_MEMORY_CHECK_INTERVAL_SECONDS" "${JUSTNEWS_MEMORY_CHECK_INTERVAL_SECONDS:-5}"
upsert_env "JUSTNEWS_MEMORY_ACTION_COOLDOWN_SECONDS" "${JUSTNEWS_MEMORY_ACTION_COOLDOWN_SECONDS:-15}"
upsert_env "JUSTNEWS_MEMORY_TERMINATE_GRACE_SECONDS" "${JUSTNEWS_MEMORY_TERMINATE_GRACE_SECONDS:-12}"
upsert_env "JUSTNEWS_MEMORY_STALE_EXIT_SECONDS" "${JUSTNEWS_MEMORY_STALE_EXIT_SECONDS:-45}"
upsert_env "JUSTNEWS_MEMORY_SOFT_DWELL_SECONDS" "${JUSTNEWS_MEMORY_SOFT_DWELL_SECONDS:-15}"
upsert_env "JUSTNEWS_MEMORY_HARD_DWELL_SECONDS" "${JUSTNEWS_MEMORY_HARD_DWELL_SECONDS:-8}"
upsert_env "JUSTNEWS_MEMORY_STATUS_LOG_INTERVAL_SECONDS" "${JUSTNEWS_MEMORY_STATUS_LOG_INTERVAL_SECONDS:-20}"

# shellcheck disable=SC1090
source "${ENV_FILE}"

# Stop any existing governor first
for pid in $(pgrep -f '/app/scripts/ops/justnews_memory_governor.py' || true); do
  kill -TERM "$pid" 2>/dev/null || true
done
sleep 1

# Build fresh PID map from listening agent ports
# shellcheck disable=SC1090
source "${ROOT_DIR}/infrastructure/agents_manifest.sh"
{
  echo '{"processes":['
  first=1
  for entry in "${AGENTS_MANIFEST[@]}"; do
    IFS='|' read -r name _ port <<< "$entry"
    pid="$(pid_for_port "$port" | tr -d '[:space:]')"
    if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
      continue
    fi

    critical=false
    if [[ "$name" == "mcp_bus" || "$name" == "memory" ]]; then
      critical=true
    fi

    if [[ $first -eq 0 ]]; then
      echo ','
    fi
    printf '{"name":"%s","pid":%s,"critical":%s}' "$name" "$pid" "$critical"
    first=0
  done

  publisher_pid="$(pid_for_port "${PUBLISHER_PORT:-8100}" | tr -d '[:space:]')"
  if [[ "$publisher_pid" =~ ^[0-9]+$ ]]; then
    if [[ $first -eq 0 ]]; then
      echo ','
    fi
    printf '{"name":"publisher","pid":%s,"critical":false}' "$publisher_pid"
  fi

  echo ']}'
} > "${MAPFILE}"

PYTHON_BIN="$(resolve_python)"
nohup "${PYTHON_BIN}" "${ROOT_DIR}/scripts/ops/justnews_memory_governor.py" \
  --pid-map "${MAPFILE}" \
  --log-file "${LOGFILE}" \
  --state-file "${STATEFILE}" \
  --soft-percent "${JUSTNEWS_MEMORY_SOFT_PERCENT}" \
  --hard-percent "${JUSTNEWS_MEMORY_HARD_PERCENT}" \
  --emergency-percent "${JUSTNEWS_MEMORY_EMERGENCY_PERCENT}" \
  --resume-percent "${JUSTNEWS_MEMORY_RESUME_PERCENT}" \
  --check-interval-seconds "${JUSTNEWS_MEMORY_CHECK_INTERVAL_SECONDS}" \
  --action-cooldown-seconds "${JUSTNEWS_MEMORY_ACTION_COOLDOWN_SECONDS}" \
  --terminate-grace-seconds "${JUSTNEWS_MEMORY_TERMINATE_GRACE_SECONDS}" \
  --stale-exit-seconds "${JUSTNEWS_MEMORY_STALE_EXIT_SECONDS}" \
  --soft-dwell-seconds "${JUSTNEWS_MEMORY_SOFT_DWELL_SECONDS}" \
  --hard-dwell-seconds "${JUSTNEWS_MEMORY_HARD_DWELL_SECONDS}" \
  --status-log-interval-seconds "${JUSTNEWS_MEMORY_STATUS_LOG_INTERVAL_SECONDS}" \
  >/dev/null 2>&1 &

new_pid=$!
echo "$new_pid" > "${PIDFILE}"

echo "Governor ENABLED"
echo "PID: ${new_pid}"
echo "Env: ${ENV_FILE} (JUSTNEWS_MEMORY_GOVERNOR_ENABLED=1)"
echo "Log: ${LOGFILE}"
