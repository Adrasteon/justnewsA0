#!/usr/bin/env bash
# Install/upgrade the node-level OpenTelemetry Collector for JustNews GPU hosts.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "This installer must be run as root (sudo)." >&2
  exit 1
fi

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OTEL_VERSION=${OTELCOL_VERSION:-0.103.1}
ARCH=$(uname -m)
case "${ARCH}" in
  x86_64|amd64)
    TAR_NAME="otelcol-contrib_${OTEL_VERSION}_linux_amd64.tar.gz"
    ;;
  aarch64|arm64)
    TAR_NAME="otelcol-contrib_${OTEL_VERSION}_linux_arm64.tar.gz"
    ;;
  *)
    echo "Unsupported architecture: ${ARCH}" >&2
    exit 1
    ;;
esac

: "${OTEL_BASE_URL:=https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download}"
DOWNLOAD_URL="${OTEL_BASE_URL}/v${OTEL_VERSION}/${TAR_NAME}"
TARGET_BIN=/usr/local/bin/otelcol-contrib
TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "Downloading ${DOWNLOAD_URL}" >&2
curl -fsSL "${DOWNLOAD_URL}" -o "${TMP_DIR}/${TAR_NAME}"
tar -xzf "${TMP_DIR}/${TAR_NAME}" -C "${TMP_DIR}" otelcol-contrib
install -m 0755 "${TMP_DIR}/otelcol-contrib" "${TARGET_BIN}"

CONFIG_DIR=/etc/justnews/monitoring/otel
install -d -m 0755 /etc/justnews/monitoring
install -d -m 0755 "${CONFIG_DIR}"
install -m 0644 "${REPO_ROOT}/infrastructure/monitoring/otel/node-collector-config.yaml" \
  "${CONFIG_DIR}/node-collector-config.yaml"
install -m 0644 "${REPO_ROOT}/infrastructure/systemd/units/justnews-otel-node.service" \
  /etc/systemd/system/justnews-otel-node.service

ENV_FILE="${CONFIG_DIR}/node.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  cat <<'EOF' > "${ENV_FILE}"
# Environment overrides for the node-level otel collector
OTEL_NODE_CONFIG=/etc/justnews/monitoring/otel/node-collector-config.yaml
OTEL_SERVICE_NAME=justnews-node
DEPLOYMENT_ENVIRONMENT=dev
OTEL_UPSTREAM_ENDPOINT=127.0.0.1:4319
OTEL_UPSTREAM_INSECURE=true
OTEL_UPSTREAM_AUTH=
PROM_REMOTE_WRITE_URL=http://127.0.0.1:9090/api/v1/write
PROM_REMOTE_WRITE_INSECURE=true
PROM_REMOTE_WRITE_TENANT=justnews
OTEL_DCGM_TARGET=127.0.0.1:9400
OTEL_DCGM_SCRAPE_INTERVAL=15s
OTEL_NODE_EXPORTER_TARGET=127.0.0.1:9100
OTEL_NODE_SCRAPE_INTERVAL=15s
OTEL_HOSTMETRICS_INTERVAL=30s
OTEL_LOG_LEVEL=info
OTEL_MEMORY_LIMIT_MIB=512
EOF
fi

ensure_env_var() {
  local key="$1"
  local value="$2"
  if ! grep -q "^${key}=" "${ENV_FILE}"; then
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

ensure_env_var OTEL_NODE_CONFIG /etc/justnews/monitoring/otel/node-collector-config.yaml
ensure_env_var OTEL_SERVICE_NAME justnews-node
ensure_env_var DEPLOYMENT_ENVIRONMENT dev
ensure_env_var OTEL_UPSTREAM_ENDPOINT 127.0.0.1:4319
ensure_env_var OTEL_UPSTREAM_INSECURE true
ensure_env_var OTEL_UPSTREAM_AUTH ""
ensure_env_var PROM_REMOTE_WRITE_URL http://127.0.0.1:9090/api/v1/write
ensure_env_var PROM_REMOTE_WRITE_INSECURE true
ensure_env_var PROM_REMOTE_WRITE_TENANT justnews
ensure_env_var OTEL_DCGM_TARGET 127.0.0.1:9400
ensure_env_var OTEL_DCGM_SCRAPE_INTERVAL 15s
ensure_env_var OTEL_NODE_EXPORTER_TARGET 127.0.0.1:9100
ensure_env_var OTEL_NODE_SCRAPE_INTERVAL 15s
ensure_env_var OTEL_HOSTMETRICS_INTERVAL 30s
ensure_env_var OTEL_LOG_LEVEL info
ensure_env_var OTEL_MEMORY_LIMIT_MIB 512

systemctl daemon-reload
systemctl enable --now justnews-otel-node.service

echo "Node-level OpenTelemetry Collector installed and started." >&2
