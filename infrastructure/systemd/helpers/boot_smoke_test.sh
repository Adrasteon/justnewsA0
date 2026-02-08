#!/usr/bin/env bash
# boot_smoke_test.sh — Lightweight boot-time health smoke test
#
# Purpose: After system boot (and services start), quickly verify key endpoints
# without being noisy or blocking boot. Outputs a concise PASS/FAIL summary and
# always exits 0 so timers don’t flap.
#
# Dependencies: bash, curl. jq is optional (pretty-print if available).

set -euo pipefail

BASE_URL="http://127.0.0.1"
ORCH_PORT=8014
BUS_PORT=8000
AGENT_PORTS=(8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8011 8012 8013 8014 8015 8016)

TIMEOUT_SEC=${SMOKE_TIMEOUT_SEC:-2}
RETRIES=${SMOKE_RETRIES:-5}
SLEEP_BETWEEN=${SMOKE_SLEEP_BETWEEN:-2}

log() { echo "[boot-smoke] $*"; }

curl_ok() {
  local url="$1"
  curl -fsS --max-time "$TIMEOUT_SEC" "$url" >/dev/null 2>&1
}

wait_ready() {
  local name="$1"; shift
  local url="$1"; shift
  local attempts=0
  while (( attempts < RETRIES )); do
    if curl_ok "$url"; then
      log "OK: $name is ready ($url)"
      return 0
    fi
    attempts=$((attempts+1))
    sleep "$SLEEP_BETWEEN"
  done
  log "FAIL: $name not ready after $RETRIES attempts ($url)"
  return 1
}

results=()
pass_count=0
fail_count=0

# 1) Orchestrator readiness
if wait_ready "gpu_orchestrator /ready" "$BASE_URL:$ORCH_PORT/ready"; then
  results+=("gpu_orchestrator:PASS")
  ((pass_count++))
else
  results+=("gpu_orchestrator:FAIL")
  ((fail_count++))
fi

# 2) MCP Bus health (optional: do not block overall)
if curl_ok "$BASE_URL:$BUS_PORT/health"; then
  log "OK: mcp_bus /health"
  results+=("mcp_bus:PASS")
  ((pass_count++))
else
  log "WARN: mcp_bus /health not ready"
  results+=("mcp_bus:FAIL")
  ((fail_count++))
fi

# 3) Selected agents health (quick ping)
for p in "${AGENT_PORTS[@]}"; do
  if curl_ok "$BASE_URL:$p/health"; then
    log "OK: agent@$p /health"
    results+=("agent@$p:PASS")
    ((pass_count++))
  else
    log "WARN: agent@$p /health not ready"
    results+=("agent@$p:FAIL")
    ((fail_count++))
  fi
done

log "SUMMARY: PASS=$pass_count FAIL=$fail_count"
printf '%s\n' "${results[@]}" | tr '\n' ' ' | sed 's/ $//'

# Always exit 0 to avoid timer flapping; operators can review journal.
exit 0
