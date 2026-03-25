#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=${ROOT_DIR:-/app}
INDEX_DIR=${INDEX_DIR:-.cache/code_index}
TELEMETRY_PATH=${TELEMETRY_PATH:-run/indexing_telemetry.jsonl}
BOOTSTRAP_JSON_PATH=${BOOTSTRAP_JSON_PATH:-run/index_bootstrap_daily.json}

cd "$ROOT_DIR"

echo "[1/5] Session init bootstrap"
bash scripts/indexing/session_chat_init.sh

echo "[2/5] Incremental index refresh"
python3 scripts/indexing/build_code_index.py \
  --root . \
  --index-dir "$INDEX_DIR" \
  --telemetry-path "$TELEMETRY_PATH"

echo "[3/5] Bootstrap context snapshot"
mkdir -p "$(dirname "$BOOTSTRAP_JSON_PATH")"
python3 scripts/indexing/bootstrap_context.py \
  --root . \
  --index-dir "$INDEX_DIR" \
  --telemetry-path "$TELEMETRY_PATH" \
  --json > "$BOOTSTRAP_JSON_PATH"

echo "[4/5] Telemetry summary"
python3 scripts/indexing/telemetry_summary.py \
  --path "$TELEMETRY_PATH" \
  --last 500

echo "[5/5] Suggested benchmark prompt"
echo "Use .github/prompts/justnews-hermes-benchmark.prompt.md for weekly architecture regression checks."

echo "Done. Bootstrap JSON: $BOOTSTRAP_JSON_PATH"
