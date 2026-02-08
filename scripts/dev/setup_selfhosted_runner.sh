#!/usr/bin/env bash
# Prepare a self-hosted runner for systemd-nspawn E2E tests.
# - Installs required packages and optionally builds a base container cache
#   under /var/lib/ci_cache/justnews_base.tar.gz for faster CI runs.

set -euo pipefail

CACHE_DIR=${CACHE_DIR:-/var/lib/ci_cache}
CACHE_TAR=${CACHE_DIR}/justnews_test_base.tar.gz
MACHINE_BASE=/var/lib/machines/justnews-test
SUITE=${SUITE:-24.04}

function require_root(){
  if [[ $(id -u) -ne 0 ]]; then
    echo "This script requires root. Run as sudo." >&2
    exit 1
  fi
}

require_root

echo "Installing system tooling (debootstrap, systemd-container, rsync)..."
apt-get update -y
apt-get install -y debootstrap systemd-container rsync tar bc --no-install-recommends

mkdir -p ${CACHE_DIR}

if [[ -f "${CACHE_TAR}" ]]; then
  echo "Cache already exists at ${CACHE_TAR}. Nothing more to do.";
  exit 0
fi

if [[ -d "${MACHINE_BASE}" ]]; then
  echo "Base machine exists at ${MACHINE_BASE}. Creating cache tarball..."
else
  echo "Bootstrapping base machine at ${MACHINE_BASE}";
  mkdir -p ${MACHINE_BASE}
  debootstrap --variant=minbase --arch=$(dpkg --print-architecture) ${SUITE} "${MACHINE_BASE}" http://archive.ubuntu.com/ubuntu
  chroot "${MACHINE_BASE}" /bin/bash -lc "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y systemd-sysv dbus locales && locale-gen C.UTF-8"
fi

  echo "Packing base machine into cache ${CACHE_TAR} (may take a few minutes)..."
  tar -czf "${CACHE_TAR}" -C /var/lib/machines justnews-test
echo "Cache created at ${CACHE_TAR}"

echo "Runner prepared. The systemd-nspawn workflow can reuse ${CACHE_TAR} to speed up runs."

exit 0
