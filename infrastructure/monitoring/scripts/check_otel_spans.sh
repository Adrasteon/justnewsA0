#!/usr/bin/env bash
set -euo pipefail

# Usage: check_otel_spans.sh <metrics_url> <metric_name>
# Example: check_otel_spans.sh http://localhost:18889/metrics otelcol_exporter_sent_spans

METRICS_URL=${1:-"http://localhost:${NODE_METRICS_PORT:-18889}/metrics"}
METRIC_NAME=${2:-"otelcol_exporter_sent_spans"}
TIMEOUT_SECS=${3:-60}
SLEEP_SECS=${4:-5}

echo "Checking metrics endpoint $METRICS_URL for metric '$METRIC_NAME' (timeout ${TIMEOUT_SECS}s)"

attempts=$(( (TIMEOUT_SECS + SLEEP_SECS - 1) / SLEEP_SECS ))

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

for i in $(seq 1 $attempts); do
  echo "Attempt $i of $attempts"
  if curl -sSf "$METRICS_URL" -o "$tmpfile"; then
    # find the metric line (with optional labels) and take the last matching value
    val=$(grep -E "^${METRIC_NAME}(\{.*\})?\s+" "$tmpfile" | awk '{print $2}' | tail -n1 || true)
    if [ -n "$val" ]; then
      # use awk numeric comparison to support floats
      if awk -v v="$val" 'BEGIN {exit !(v+0>0)}'; then
        echo "Metric ${METRIC_NAME} > 0 (value=${val})"
        exit 0
      else
        echo "Metric ${METRIC_NAME} present but not > 0 (value=${val})"
      fi
    else
      echo "Metric ${METRIC_NAME} not yet present in metrics output"
    fi
  else
    echo "Metrics endpoint not yet available (curl failed)"
  fi
  sleep "$SLEEP_SECS"
done

echo "Timed out waiting for ${METRIC_NAME} > 0 at ${METRICS_URL}"
exit 1
