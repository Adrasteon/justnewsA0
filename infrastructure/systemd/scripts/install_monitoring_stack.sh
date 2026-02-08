#!/usr/bin/env bash
set -euo pipefail

show_usage() {
  cat <<'EOF'
Usage: install_monitoring_stack.sh [options]

Copy Prometheus and Grafana systemd assets into place and optionally enable the
services.

Options:
  --config-dir <path>   Destination for generated monitoring config
                        (default: /etc/justnews/monitoring)
  --env-file <path>     Environment file consumed by the monitoring units
                        (default: /etc/justnews/monitoring.env)
  --install-binaries    Download and install Prometheus, Grafana, and node_exporter
                        under /opt/justnews/monitoring (requires curl & tar)
  --install-root <path> Root directory for downloaded binaries
                        (default: /opt/justnews/monitoring)
  --prometheus-version <ver>
                        Prometheus version tag (default: 2.53.0)
  --grafana-version <ver>
                        Grafana OSS version tag (default: 11.1.3)
  --node-exporter-version <ver>
                        node_exporter version tag (default: 1.8.1)
  --enable              Enable services after assets are installed
  --start               Enable and start/restart services after install
  --force               Overwrite existing config files instead of creating
                        timestamped backups
  -h, --help            Show this message
EOF
}

CONFIG_DIR=/etc/justnews/monitoring
ENV_FILE=/etc/justnews/monitoring.env
INSTALL_BINARIES=false
INSTALL_ROOT=/opt/justnews/monitoring
SYMLINK_DIR=/usr/local/bin
PROMETHEUS_VERSION=2.53.0
GRAFANA_VERSION=11.1.3
NODE_EXPORTER_VERSION=1.8.1
ENABLE_UNITS=false
START_UNITS=false
FORCE=false

require_value() {
  local flag="$1"
  local value="$2"
  if [[ -z "$value" || "$value" == "--"* ]]; then
    echo "[ERROR] Option $flag requires a value" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config-dir)
      require_value "$1" "${2:-}"
      CONFIG_DIR="$2"
      shift 2
      ;;
    --env-file)
      require_value "$1" "${2:-}"
      ENV_FILE="$2"
      shift 2
      ;;
    --install-binaries)
      INSTALL_BINARIES=true
      shift
      ;;
    --install-root)
      require_value "$1" "${2:-}"
      INSTALL_ROOT="$2"
      shift 2
      ;;
    --prometheus-version)
      require_value "$1" "${2:-}"
      PROMETHEUS_VERSION="$2"
      shift 2
      ;;
    --grafana-version)
      require_value "$1" "${2:-}"
      GRAFANA_VERSION="$2"
      shift 2
      ;;
    --node-exporter-version)
      require_value "$1" "${2:-}"
      NODE_EXPORTER_VERSION="$2"
      shift 2
      ;;
    --enable)
      ENABLE_UNITS=true
      shift
      ;;
    --start)
      ENABLE_UNITS=true
      START_UNITS=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    -h|--help)
      show_usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_usage >&2
      exit 1
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] Run this script as root (sudo)." >&2
  exit 1
fi

if ! id -u justnews >/dev/null 2>&1; then
  echo "[ERROR] The 'justnews' system user is required." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ASSET_ROOT="$REPO_ROOT/infrastructure/systemd/monitoring"
DASHBOARD_SRC="$REPO_ROOT/monitoring/dashboards/generated"
EXAMPLE_ENV="$REPO_ROOT/infrastructure/systemd/examples/monitoring.env.example"

if [[ ! -d "$ASSET_ROOT" ]]; then
  echo "[ERROR] Monitoring assets not found under $ASSET_ROOT" >&2
  exit 1
fi

mkdir -p "$CONFIG_DIR"
mkdir -p "$CONFIG_DIR/grafana"
mkdir -p "$CONFIG_DIR/grafana/dashboards"
mkdir -p "$CONFIG_DIR/grafana/provisioning"

copy_file() {
  local src="$1" dest="$2"
  if [[ -e "$dest" && $FORCE == false ]]; then
    local backup="${dest}.bak.$(date +%s)"
    echo "[INFO] Existing $(basename "$dest") detected; writing backup to $backup"
    cp -f "$dest" "$backup"
  fi
  install -D -m 0644 "$src" "$dest"
}

copy_tree() {
  local src="$1" dest="$2"
  while IFS= read -r -d '' file; do
    local rel="${file#$src/}"
    install -D -m 0644 "$file" "$dest/$rel"
  done < <(find "$src" -type f -print0)
}

update_env_var() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s#^${key}=.*#${key}=${value}#" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  fi
}

ensure_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Required command '$cmd' not found in PATH" >&2
    exit 1
  fi
}

download_and_unpack() {
  local url="$1" dest_dir="$2" expected_dir_prefix="$3" alt_prefix="${4:-}"
  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  local archive="$tmp/$(basename "$url")"
  echo "[INFO] Downloading $(basename "$url")"
  curl -fsSL "$url" -o "$archive"
  tar -xf "$archive" -C "$tmp"
  local extracted_dir
  extracted_dir="$(find "$tmp" -maxdepth 1 -type d -name "${expected_dir_prefix}*" -print | head -n1)"
  if [[ -z "$extracted_dir" && -n "$alt_prefix" ]]; then
    extracted_dir="$(find "$tmp" -maxdepth 1 -type d -name "${alt_prefix}*" -print | head -n1)"
  fi
  if [[ -z "$extracted_dir" ]]; then
    echo "[ERROR] Failed to extract archive from $url" >&2
    exit 1
  fi
  rm -rf "$dest_dir"
  mkdir -p "$dest_dir"
  cp -a "$extracted_dir"/. "$dest_dir/"
  rm -rf "$tmp"
  trap - RETURN
}

install_prometheus_binary() {
  local archive_dir="$INSTALL_ROOT/prometheus-${PROMETHEUS_VERSION}"
  download_and_unpack "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz" "$archive_dir" "prometheus-${PROMETHEUS_VERSION}.linux-amd64"
  ln -sfn "$archive_dir" "$INSTALL_ROOT/prometheus"
  ln -sfn "$INSTALL_ROOT/prometheus/prometheus" "$SYMLINK_DIR/prometheus"
  ln -sfn "$INSTALL_ROOT/prometheus/promtool" "$SYMLINK_DIR/promtool"
  chmod 0755 "$INSTALL_ROOT/prometheus/prometheus" "$INSTALL_ROOT/prometheus/promtool"
}

install_grafana_binary() {
  local archive_dir="$INSTALL_ROOT/grafana-${GRAFANA_VERSION}"
  download_and_unpack "https://dl.grafana.com/oss/release/grafana-${GRAFANA_VERSION}.linux-amd64.tar.gz" "$archive_dir" "grafana-${GRAFANA_VERSION}" "grafana-v${GRAFANA_VERSION}"
  ln -sfn "$archive_dir" "$INSTALL_ROOT/grafana"
  ln -sfn "$INSTALL_ROOT/grafana/bin/grafana-server" "$SYMLINK_DIR/grafana-server"
  chmod 0755 "$INSTALL_ROOT/grafana/bin/grafana-server"
}

install_node_exporter_binary() {
  local archive_dir="$INSTALL_ROOT/node_exporter-${NODE_EXPORTER_VERSION}"
  download_and_unpack "https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz" "$archive_dir" "node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64"
  ln -sfn "$archive_dir" "$INSTALL_ROOT/node_exporter"
  ln -sfn "$INSTALL_ROOT/node_exporter/node_exporter" "$SYMLINK_DIR/node_exporter"
  chmod 0755 "$INSTALL_ROOT/node_exporter/node_exporter"
}

install_monitoring_binaries() {
  ensure_command curl
  ensure_command tar
  install -d -m 0755 "$INSTALL_ROOT"
  install -d -m 0755 "$SYMLINK_DIR"
  install_prometheus_binary
  install_grafana_binary
  install_node_exporter_binary
  update_env_var PROMETHEUS_BIN "$INSTALL_ROOT/prometheus/prometheus"
  update_env_var PROMETHEUS_CONSOLE_TEMPLATES "$INSTALL_ROOT/prometheus/consoles"
  update_env_var PROMETHEUS_CONSOLE_LIBRARIES "$INSTALL_ROOT/prometheus/console_libraries"
  update_env_var GRAFANA_BIN "$INSTALL_ROOT/grafana/bin/grafana-server"
  update_env_var GRAFANA_HOME_PATH "$INSTALL_ROOT/grafana"
  update_env_var NODE_EXPORTER_BIN "$INSTALL_ROOT/node_exporter/node_exporter"
  if ! grep -q '^NODE_EXPORTER_LISTEN_ADDRESS=' "$ENV_FILE" 2>/dev/null; then
    update_env_var NODE_EXPORTER_LISTEN_ADDRESS "0.0.0.0:9100"
  fi
}

copy_file "$ASSET_ROOT/prometheus.yml" "$CONFIG_DIR/prometheus.yml"
copy_file "$ASSET_ROOT/grafana.ini" "$CONFIG_DIR/grafana.ini"
copy_tree "$ASSET_ROOT/grafana/provisioning" "$CONFIG_DIR/grafana/provisioning"

if [[ -d "$DASHBOARD_SRC" ]]; then
  copy_tree "$DASHBOARD_SRC" "$CONFIG_DIR/grafana/dashboards"
else
  echo "[WARN] No generated dashboards found at $DASHBOARD_SRC" >&2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  install -D -m 0640 "$EXAMPLE_ENV" "$ENV_FILE"
  echo "[INFO] Created monitoring environment file from template: $ENV_FILE"
else
  echo "[INFO] Monitoring environment file already present: $ENV_FILE"
fi

if [[ "$INSTALL_BINARIES" == true ]]; then
  install_monitoring_binaries
fi

set -a
source "$ENV_FILE"
set +a

PROM_DATA="${PROMETHEUS_DATA_DIR:-/var/lib/justnews/prometheus}"
GRAFANA_DATA="${GF_PATHS_DATA:-/var/lib/justnews/grafana}"
GRAFANA_LOGS="${GF_PATHS_LOGS:-/var/log/justnews/grafana}"
GRAFANA_PLUGINS="${GF_PATHS_PLUGINS:-/var/lib/justnews/grafana/plugins}"
NODE_TEXTFILE_DIR="${NODE_EXPORTER_TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}"

install -d -m 0750 -o justnews -g justnews "$PROM_DATA"
install -d -m 0750 -o justnews -g justnews "$GRAFANA_DATA"
install -d -m 0750 -o justnews -g justnews "$GRAFANA_LOGS"
install -d -m 0750 -o justnews -g justnews "$GRAFANA_PLUGINS"
install -d -m 0775 -o justnews -g justnews "$NODE_TEXTFILE_DIR"

declare -a missing_bins=()
if [[ -z "${PROMETHEUS_BIN:-}" ]]; then
  missing_bins+=("Prometheus (not configured)")
elif [[ ! -x "$PROMETHEUS_BIN" ]]; then
  missing_bins+=("Prometheus ($PROMETHEUS_BIN)")
fi

if [[ -z "${GRAFANA_BIN:-}" ]]; then
  missing_bins+=("Grafana (not configured)")
elif [[ ! -x "$GRAFANA_BIN" ]]; then
  missing_bins+=("Grafana ($GRAFANA_BIN)")
fi

if [[ -z "${NODE_EXPORTER_BIN:-}" ]]; then
  missing_bins+=("node_exporter (not configured)")
elif [[ ! -x "$NODE_EXPORTER_BIN" ]]; then
  missing_bins+=("node_exporter ($NODE_EXPORTER_BIN)")
fi

if [[ ${#missing_bins[@]} -gt 0 ]]; then
  if [[ "$START_UNITS" == true ]]; then
    echo "[ERROR] Cannot start monitoring services because the following binaries are missing or not executable:" >&2
    printf '  - %s\n' "${missing_bins[@]}" >&2
    exit 1
  else
    echo "[WARN] Missing binaries detected: ${missing_bins[*]}. Install them or update $ENV_FILE before starting services." >&2
  fi
fi

UNIT_DIR=/etc/systemd/system
install -D -m 0644 "$REPO_ROOT/infrastructure/systemd/units/justnews-prometheus.service" "$UNIT_DIR/justnews-prometheus.service"
install -D -m 0644 "$REPO_ROOT/infrastructure/systemd/units/justnews-grafana.service" "$UNIT_DIR/justnews-grafana.service"
install -D -m 0644 "$REPO_ROOT/infrastructure/systemd/units/justnews-node-exporter.service" "$UNIT_DIR/justnews-node-exporter.service"

echo "[INFO] Installed systemd unit files for Prometheus, Grafana, and node_exporter"

systemctl daemon-reload

declare -a targets
if [[ $ENABLE_UNITS == true ]]; then
  targets=(justnews-node-exporter.service justnews-prometheus.service justnews-grafana.service)
  systemctl enable "${targets[@]}"
  echo "[INFO] Enabled monitoring units"
  if [[ $START_UNITS == true ]]; then
    systemctl restart justnews-node-exporter.service
    systemctl restart justnews-prometheus.service
    systemctl restart justnews-grafana.service
    echo "[INFO] Restarted monitoring units"
  fi
else
  echo "[INFO] Units installed but not enabled; run 'sudo systemctl enable --now justnews-node-exporter.service justnews-prometheus.service justnews-grafana.service' when ready."
fi

echo "[SUCCESS] Monitoring assets deployed to $CONFIG_DIR"
