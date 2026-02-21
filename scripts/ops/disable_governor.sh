#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/global.env"
PIDFILE="/tmp/justnews_services_logs/memory_governor/justnews_memory_governor.pid"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found"
  exit 1
fi

if grep -qE '^JUSTNEWS_MEMORY_GOVERNOR_ENABLED=' "${ENV_FILE}"; then
  sed -i 's|^JUSTNEWS_MEMORY_GOVERNOR_ENABLED=.*|JUSTNEWS_MEMORY_GOVERNOR_ENABLED=0|' "${ENV_FILE}"
else
  printf '\nJUSTNEWS_MEMORY_GOVERNOR_ENABLED=0\n' >> "${ENV_FILE}"
fi

for pid in $(pgrep -f '/app/scripts/ops/justnews_memory_governor.py' || true); do
  kill -TERM "$pid" 2>/dev/null || true
done
sleep 1

if [[ -f "${PIDFILE}" ]]; then
  rm -f "${PIDFILE}"
fi

echo "Governor DISABLED"
echo "Env: ${ENV_FILE} (JUSTNEWS_MEMORY_GOVERNOR_ENABLED=0)"
