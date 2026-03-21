#!/usr/bin/env bash

set -euo pipefail

LM_BASE_URL="${LM_BASE_URL:-http://host.docker.internal:1234/v1}"
QDRANT_URL="${QDRANT_URL:-http://host.docker.internal:6333}"
CHAT_MODEL_ID="${CHAT_MODEL_ID:-google/gemma-3-12b}"
EMBED_MODEL_ID="${EMBED_MODEL_ID:-text-embedding-nomic-embed-text-v1.5}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-8}"

PASS_COUNT=0
FAIL_COUNT=0

usage() {
  cat <<'EOF'
Usage: scripts/verify_roo_index_setup.sh

Environment overrides:
  LM_BASE_URL       LM Studio OpenAI-compatible base URL (default: http://host.docker.internal:1234/v1)
  QDRANT_URL        Qdrant base URL (default: http://host.docker.internal:6333)
  CHAT_MODEL_ID     Chat model id expected in /models (default: google/gemma-3-12b)
  EMBED_MODEL_ID    Embedding model id expected in /models (default: text-embedding-nomic-embed-text-v1.5)
  TIMEOUT_SECONDS   Curl timeout in seconds (default: 8)
EOF
}

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "PASS: $1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  echo "FAIL: $1"
}

require_tools() {
  local missing=0
  for tool in curl grep; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
      echo "Missing required tool: ${tool}"
      missing=1
    fi
  done
  if [[ "${missing}" -ne 0 ]]; then
    exit 2
  fi
}

fetch_json() {
  local url="$1"
  local output
  if ! output="$(curl -fsS --connect-timeout 3 --max-time "${TIMEOUT_SECONDS}" "${url}")"; then
    return 1
  fi
  printf '%s' "${output}"
}

check_lm_models() {
  local models_url="${LM_BASE_URL%/}/models"
  local body

  if ! body="$(fetch_json "${models_url}")"; then
    fail "LM Studio models endpoint unreachable at ${models_url}"
    return
  fi

  pass "LM Studio models endpoint reachable at ${models_url}"

  if printf '%s' "${body}" | grep -Fq "${CHAT_MODEL_ID}"; then
    pass "Chat model id is available: ${CHAT_MODEL_ID}"
  else
    fail "Chat model id not found in LM Studio models list: ${CHAT_MODEL_ID}"
  fi

  if printf '%s' "${body}" | grep -Fq "${EMBED_MODEL_ID}"; then
    pass "Embedding model id is available: ${EMBED_MODEL_ID}"
  else
    fail "Embedding model id not found in LM Studio models list: ${EMBED_MODEL_ID}"
  fi
}

check_lm_embeddings() {
  local emb_url="${LM_BASE_URL%/}/embeddings"
  local payload

  payload="$(cat <<EOF
{"model":"${EMBED_MODEL_ID}","input":["roo index verification ping"]}
EOF
)"

  if curl -fsS --connect-timeout 3 --max-time "${TIMEOUT_SECONDS}" \
    -H 'Content-Type: application/json' \
    -d "${payload}" \
    "${emb_url}" >/dev/null; then
    pass "LM Studio embeddings endpoint is working at ${emb_url}"
  else
    fail "LM Studio embeddings request failed at ${emb_url}"
  fi
}

check_qdrant() {
  local collections_url="${QDRANT_URL%/}/collections"
  local body

  if ! body="$(fetch_json "${collections_url}")"; then
    fail "Qdrant endpoint unreachable at ${collections_url}"
    return
  fi

  if printf '%s' "${body}" | grep -Fq '"status":"ok"'; then
    pass "Qdrant collections endpoint is healthy at ${collections_url}"
  else
    fail "Qdrant responded but did not return status ok at ${collections_url}"
  fi
}

print_summary() {
  echo
  echo "Checks complete: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
  fi
}

main() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
    usage
    exit 0
  fi

  require_tools
  check_lm_models
  check_lm_embeddings
  check_qdrant
  print_summary
}

main "$@"