#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BIN_DIR="$REPO_ROOT/infrastructure/monitoring/bin"
CONFIG_FILE="$REPO_ROOT/infrastructure/monitoring/otel/dev-collector-config.yaml"
OTEL_BIN="$BIN_DIR/otelcol-contrib"

# Ensure binary exists
if [ ! -f "$OTEL_BIN" ]; then
    echo "OTel Collector binary not found at $OTEL_BIN"
    echo "Downloading..."
    mkdir -p "$BIN_DIR"
    TEMP_DIR=$(mktemp -d)
    curl -L -o "$TEMP_DIR/otelcol.tar.gz" https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.81.0/otelcol-contrib_0.81.0_linux_amd64.tar.gz
    tar -xvf "$TEMP_DIR/otelcol.tar.gz" -C "$TEMP_DIR"
    mv "$TEMP_DIR/otelcol-contrib" "$OTEL_BIN"
    rm -rf "$TEMP_DIR"
    chmod +x "$OTEL_BIN"
fi

# Check and clear ports
params=(4317 4318 8888 8889)
for port in "${params[@]}"; do
    if fuser "$port/tcp" >/dev/null 2>&1; then
        echo "Port $port is in use. Killing process..."
        fuser -k -TERM "$port/tcp" >/dev/null 2>&1 || true
    fi
done

# Wait for cleanup
sleep 1

echo "Starting OTel Collector with config: $CONFIG_FILE"
echo "Sending output to stdout (traces will be logged)..."

"$OTEL_BIN" --config "$CONFIG_FILE"
