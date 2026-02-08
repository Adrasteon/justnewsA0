#!/usr/bin/env bash
# Install/upgrade the central OpenTelemetry Collector fan-out tier.
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
install -m 0644 "${REPO_ROOT}/infrastructure/monitoring/otel/central-collector-config.yaml" \
  "${CONFIG_DIR}/central-collector-config.yaml"
install -m 0644 "${REPO_ROOT}/infrastructure/systemd/units/justnews-otel-central.service" \
  /etc/systemd/system/justnews-otel-central.service

ENV_FILE="${CONFIG_DIR}/central.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  cat <<'EOF' > "${ENV_FILE}"
# Environment overrides for the central otel collector
OTEL_CENTRAL_CONFIG=/etc/justnews/monitoring/otel/central-collector-config.yaml
OTEL_CENTRAL_GRPC_ENDPOINT=0.0.0.0:4319
OTEL_CENTRAL_HTTP_ENDPOINT=0.0.0.0:4320
OTEL_SERVICE_NAME=justnews-central-collector
DEPLOYMENT_ENVIRONMENT=dev
PROM_REMOTE_WRITE_URL=http://127.0.0.1:9090/api/v1/write
PROM_REMOTE_WRITE_INSECURE=true
PROM_REMOTE_WRITE_TENANT=justnews
TEMPO_ENDPOINT=http://127.0.0.1:4318
TEMPO_INSECURE=true
JAEGER_ENDPOINT=http://127.0.0.1:4318
JAEGER_INSECURE=true
LOKI_ENDPOINT=http://127.0.0.1:3100/loki/api/v1/push
LOKI_INSECURE=true
OTEL_LOG_LEVEL=info
OTEL_MEMORY_LIMIT_MIB=1024
EOF
fi

ensure_env_var() {
  local key="$1"
  local value="$2"
  if ! grep -q "^${key}=" "${ENV_FILE}"; then
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

ensure_env_var OTEL_CENTRAL_CONFIG /etc/justnews/monitoring/otel/central-collector-config.yaml
ensure_env_var OTEL_CENTRAL_GRPC_ENDPOINT 0.0.0.0:4319
ensure_env_var OTEL_CENTRAL_HTTP_ENDPOINT 0.0.0.0:4320
ensure_env_var OTEL_SERVICE_NAME justnews-central-collector
ensure_env_var DEPLOYMENT_ENVIRONMENT dev
ensure_env_var PROM_REMOTE_WRITE_URL http://127.0.0.1:9090/api/v1/write
ensure_env_var PROM_REMOTE_WRITE_INSECURE true
ensure_env_var PROM_REMOTE_WRITE_TENANT justnews
ensure_env_var TEMPO_ENDPOINT http://127.0.0.1:4318
ensure_env_var TEMPO_INSECURE true
ensure_env_var JAEGER_ENDPOINT http://127.0.0.1:4318
ensure_env_var JAEGER_INSECURE true
ensure_env_var LOKI_ENDPOINT http://127.0.0.1:3100/loki/api/v1/push
ensure_env_var LOKI_INSECURE true
ensure_env_var OTEL_LOG_LEVEL info
ensure_env_var OTEL_MEMORY_LIMIT_MIB 1024

systemctl daemon-reload
systemctl enable --now justnews-otel-central.service

echo "Central OpenTelemetry Collector installed and started." >&2
