#!/usr/bin/env bash
# Install the NVIDIA DCGM exporter binary and configure the JustNews systemd unit.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "This installer must be run as root (use sudo)." >&2
  exit 1
fi

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TARGET_BIN=/usr/local/bin/dcgm-exporter
SYSTEMD_UNIT=/etc/systemd/system/justnews-dcgm-exporter.service
MONITORING_DIR=/etc/justnews/monitoring/dcgm
ENV_FILE=/etc/justnews/dcgm-exporter.env

VERSION=${DCGM_EXPORTER_VERSION:-3.3.5}
ARCH=$(uname -m)
case "${ARCH}" in
  x86_64|amd64)
    TARBALL="dcgm-exporter_${VERSION}_linux_amd64.tar.gz"
    ;;
  aarch64|arm64)
    TARBALL="dcgm-exporter_${VERSION}_linux_arm64.tar.gz"
    ;;
  *)
    echo "Unsupported architecture: ${ARCH}" >&2
    exit 1
    ;;
endcase

: "${DCGM_EXPORTER_BASE_URL:=https://github.com/NVIDIA/dcgm-exporter/releases/download}"
DOWNLOAD_URL="${DCGM_EXPORTER_BASE_URL}/v${VERSION}/${TARBALL}"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "Downloading dcgm-exporter ${VERSION} from ${DOWNLOAD_URL}" >&2
curl -L --fail -o "${TMP_DIR}/${TARBALL}" "${DOWNLOAD_URL}"
tar -xzf "${TMP_DIR}/${TARBALL}" -C "${TMP_DIR}"
if [[ ! -x "${TMP_DIR}/dcgm-exporter" ]]; then
  echo "dcgm-exporter binary missing from archive" >&2
  exit 1
fi
install -m 0755 "${TMP_DIR}/dcgm-exporter" "${TARGET_BIN}"

install -d -m 0755 /etc/justnews
install -d -m 0755 "${MONITORING_DIR}"
install -m 0644 "${REPO_ROOT}/infrastructure/systemd/monitoring/dcgm/metrics_default.csv" "${MONITORING_DIR}/metrics_default.csv"

if [[ ! -f "${ENV_FILE}" ]]; then
  cat <<'EOF' > "${ENV_FILE}"
# Optional overrides for the JustNews DCGM exporter systemd unit
# Example: DCGM_EXPORTER_EXTRA_FLAGS="--collectors /etc/justnews/monitoring/dcgm/profiler_metrics.csv"
#DCGM_EXPORTER_LISTEN_ADDRESS=0.0.0.0
#DCGM_EXPORTER_PORT=9400
#DCGM_EXPORTER_METRICS_FILE=/etc/justnews/monitoring/dcgm/metrics_default.csv
#DCGM_EXPORTER_EXTRA_FLAGS=
EOF
fi

install -m 0644 "${REPO_ROOT}/infrastructure/systemd/units/justnews-dcgm-exporter.service" "${SYSTEMD_UNIT}"
systemctl daemon-reload
systemctl enable --now justnews-dcgm-exporter.service

echo "dcgm-exporter installed at ${TARGET_BIN} and justnews-dcgm-exporter.service is running." >&2
