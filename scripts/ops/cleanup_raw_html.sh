#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR=${SERVICE_DIR:-$(pwd)}
RAW_DIR=${JUSTNEWS_RAW_HTML_DIR:-${SERVICE_DIR}/archive_storage/raw_html}
RETENTION_DAYS=${RAW_HTML_RETENTION_DAYS:-90}

if [[ ! -d "$RAW_DIR" ]]; then
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Raw html dir not found: $RAW_DIR" >&2
  exit 1
fi

# Delete files older than retention
find "$RAW_DIR" -type f -mtime +$RETENTION_DAYS -print -delete

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] cleaned old raw html files older than $RETENTION_DAYS days"
