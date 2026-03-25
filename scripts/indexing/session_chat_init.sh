#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=${ROOT_DIR:-/app}
INDEX_DIR=${INDEX_DIR:-.cache/code_index}
TELEMETRY_PATH=${TELEMETRY_PATH:-run/indexing_telemetry.jsonl}
CHAT_MODEL_BINDING_PATH=${CHAT_MODEL_BINDING_PATH:-run/copilot_chat_model.env}
BOOTSTRAP_CMD=(python3 scripts/indexing/bootstrap_context.py --root . --index-dir "$INDEX_DIR" --telemetry-path "$TELEMETRY_PATH" --json)
DAEMON_SCRIPT=scripts/indexing/index_autoupdate_daemon.sh

cd "$ROOT_DIR"

# Build index on first run if artifacts are missing.
if [[ ! -f "$INDEX_DIR/manifest.json" || ! -f "$INDEX_DIR/entries.jsonl" ]]; then
  python3 scripts/indexing/build_code_index.py --root . --index-dir "$INDEX_DIR" --telemetry-path "$TELEMETRY_PATH" >/dev/null 2>&1 || true
fi

# Persist selected chat model to make tokenizer behavior deterministic for this session.
mkdir -p "$(dirname "$CHAT_MODEL_BINDING_PATH")"
resolved_chat_model=""
resolved_chat_model_source=""
for var_name in COPILOT_CHAT_MODEL GITHUB_COPILOT_CHAT_MODEL VSCODE_COPILOT_CHAT_MODEL CHAT_MODEL GITHUB_COPILOT_MODEL; do
  value="${!var_name-}"
  if [[ -n "$value" ]]; then
    resolved_chat_model="$value"
    resolved_chat_model_source="env:${var_name}"
    break
  fi
done

if [[ -z "$resolved_chat_model" ]]; then
  resolved_chat_model="gpt-5.3-codex"
  resolved_chat_model_source="bootstrap-default"
fi

{
  printf 'COPILOT_CHAT_MODEL=%q\n' "$resolved_chat_model"
  printf 'COPILOT_CHAT_MODEL_SOURCE=%q\n' "$resolved_chat_model_source"
} > "$CHAT_MODEL_BINDING_PATH"

# Bootstrap context to refresh session visibility and telemetry snapshot.
"${BOOTSTRAP_CMD[@]}" >/dev/null 2>&1 || true

status_output=$(bash "$DAEMON_SCRIPT" status 2>&1 || true)
if [[ "$status_output" == *"not running"* ]]; then
  bash "$DAEMON_SCRIPT" start >/dev/null 2>&1 || true
fi

bash "$DAEMON_SCRIPT" status >/dev/null 2>&1 || true
