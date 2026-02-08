#!/usr/bin/env bash
# Helper to boot a systemd-nspawn container, install redis/mariadb, copy the repo
# in and run the real E2E test suite (E2E_REAL=1). This is intended for dev machines
# or self-hosted CI runners where systemd-nspawn + machinectl are available.
#
# Usage (as root):
#   sudo scripts/dev/run_e2e_in_nspawn.sh prepare   # bootstrap container rootfs (debootstrap)
#   sudo scripts/dev/run_e2e_in_nspawn.sh start     # start the container
#   sudo scripts/dev/run_e2e_in_nspawn.sh install   # install mariadb & redis and start them
#   sudo scripts/dev/run_e2e_in_nspawn.sh sync_repo  # copy repo into container
#   sudo scripts/dev/run_e2e_in_nspawn.sh run_tests # run tests inside container (E2E_REAL=1)
#   sudo scripts/dev/run_e2e_in_nspawn.sh collect   # collect results (logs/artifacts)
#   sudo scripts/dev/run_e2e_in_nspawn.sh stop      # stop the container

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONTAINER_NAME=${CONTAINER_NAME:-justnews-test}
MACHINE_DIR=/var/lib/machines/${CONTAINER_NAME}
CACHE_DIR=${CACHE_DIR:-/var/lib/ci_cache}
CACHE_TAR=${CACHE_DIR}/justnews_test_base.tar.gz

function require_root() {
  if [[ $(id -u) -ne 0 ]]; then
    echo "This script requires root. Re-run with sudo or as root." >&2
    exit 1
  fi
}

function exists_systemd_tools() {
  command -v systemd-nspawn >/dev/null 2>&1 && command -v machinectl >/dev/null 2>&1
}

function prepare() {
  require_root
  if ! exists_systemd_tools; then
    echo "systemd-nspawn/machinectl not available. Install systemd-container package and ensure systemd-nspawn is present." >&2
    exit 1
  fi

  mkdir -p "${MACHINE_DIR}"

  if [[ -f "${CACHE_TAR}" ]]; then
    echo "Found cache ${CACHE_TAR}, extracting to ${MACHINE_DIR}"
    tar -xzf "${CACHE_TAR}" -C /var/lib/machines
    return
  fi

  echo "No cache found. Run scripts/dev/run_systemd_nspawn_env.sh create or scripts/dev/setup_selfhosted_runner.sh to bootstrap and create a cache tarball."
  exit 1
}

function start() {
  require_root
  echo "Starting container ${CONTAINER_NAME}"
  # guard if running
  machinectl list --no-legend | grep -q "^${CONTAINER_NAME} " || {
    systemd-nspawn -D "${MACHINE_DIR}" --machine=${CONTAINER_NAME} --hostname=${CONTAINER_NAME} --network-bridge= --register > /dev/null 2>&1 || true
    machinectl start ${CONTAINER_NAME} || true
  }
  echo "Waiting for machine to be responsive..."
  sleep 2
}

function install_services() {
  require_root
  echo "Installing mariadb-server and redis-server inside ${CONTAINER_NAME}"
  machinectl shell ${CONTAINER_NAME} /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y mariadb-server redis-server python3 python3-venv python3-pip rsync"
  machinectl shell ${CONTAINER_NAME} /bin/bash -lc "systemctl enable --now mariadb && systemctl enable --now redis-server"
  echo "Services started. Waiting a few seconds for services to settle..."
  sleep 5
}

function sync_repo() {
  require_root
  echo "Syncing repository into container root at /root/justnews"
  rsync -a --delete --exclude='.git' --exclude='artifacts' --exclude='archive_storage' "${ROOT_DIR}" "${MACHINE_DIR}/root/justnews"
  echo "Repository copied. Installing Python dependencies inside container..."
  machinectl shell ${CONTAINER_NAME} /bin/bash -lc "python3 -m pip install --upgrade pip && python3 -m pip install -r /root/justnews/requirements.txt" || true
}

function run_tests() {
  require_root
  echo "Running real E2E tests inside container (E2E_REAL=1)"
  # export env vars inside container, run tests, and write output to /root/justnews/output/e2e_results.txt
  machinectl shell ${CONTAINER_NAME} /bin/bash -lc "cd /root/justnews && export E2E_REAL=1 && export DB_HOST=127.0.0.1 && export DB_PORT=3306 && export REDIS_HOST=127.0.0.1 && export REDIS_PORT=6379 && pytest tests/e2e -q | tee /root/justnews/output/e2e_results.txt"
}

function collect() {
  require_root
  echo "Collecting logs/artifacts from container to ./artifacts/e2e-${CONTAINER_NAME}"
  mkdir -p "${ROOT_DIR}/artifacts/e2e-${CONTAINER_NAME}"
  rsync -a "${MACHINE_DIR}/root/justnews/output/" "${ROOT_DIR}/artifacts/e2e-${CONTAINER_NAME}/" || true
  # fetch system service logs for redis and mariadb
  machinectl shell ${CONTAINER_NAME} /bin/bash -lc "journalctl -u redis-server -n 200 > /tmp/redis.log || true; journalctl -u mariadb -n 200 > /tmp/mariadb.log || true"
  rsync -a "${MACHINE_DIR}/tmp/redis.log" "${ROOT_DIR}/artifacts/e2e-${CONTAINER_NAME}/redis.log" || true
  rsync -a "${MACHINE_DIR}/tmp/mariadb.log" "${ROOT_DIR}/artifacts/e2e-${CONTAINER_NAME}/mariadb.log" || true
  echo "Collected artifacts at artifacts/e2e-${CONTAINER_NAME}"
}

function stop() {
  require_root
  echo "Stopping container ${CONTAINER_NAME}"
  machinectl poweroff ${CONTAINER_NAME} || true
}

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <prepare|start|install|sync_repo|run_tests|collect|stop>" >&2
  exit 1
fi

case "$1" in
  prepare) prepare ;; 
  start) start ;;
  install) install_services ;;
  sync_repo) sync_repo ;;
  run_tests) run_tests ;;
  collect) collect ;;
  stop) stop ;;
  *) echo "Unknown command" >&2; exit 2 ;;
esac

exit 0
