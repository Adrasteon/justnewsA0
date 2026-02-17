#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${SERVICE_DIR:-}" ]]; then
  echo "[crawl-scheduler] SERVICE_DIR is not set" >&2
  exit 1
fi

if [[ -z "${JUSTNEWS_PYTHON:-}" ]]; then
  echo "[crawl-scheduler] JUSTNEWS_PYTHON is not set" >&2
  exit 1
fi

SCHEDULE_PATH=${CRAWL_SCHEDULE_PATH:-"$SERVICE_DIR/config/crawl_schedule.yaml"}
STATE_OUTPUT=${CRAWL_SCHEDULER_STATE:-"$SERVICE_DIR/logs/analytics/crawl_scheduler_state.json"}
SUCCESS_OUTPUT=${CRAWL_SCHEDULER_SUCCESS:-"$SERVICE_DIR/logs/analytics/crawl_scheduler_success.json"}
METRICS_OUTPUT=${CRAWL_SCHEDULER_METRICS:-"$SERVICE_DIR/logs/analytics/crawl_scheduler.prom"}
CRAWLER_URL=${CRAWLER_AGENT_URL:-"http://127.0.0.1:8015"}

cd "$SERVICE_DIR"

exec "$JUSTNEWS_PYTHON" scripts/ops/run_crawl_schedule.py \
  --schedule "$SCHEDULE_PATH" \
  --state-output "$STATE_OUTPUT" \
  --success-output "$SUCCESS_OUTPUT" \
  --metrics-output "$METRICS_OUTPUT" \
  --crawler-url "$CRAWLER_URL"
