#!/usr/bin/env bash
set -euo pipefail

# Helper to run pytest with useful test environment presets
# Usage: scripts/run_tests_with_env.sh [preset] [-- pytest args...]
# Presets: local (default), gpu, chroma-live, vllm, playwright, all

PRESET=${1:-local}
shift || true
# If a -- is present, forward everything after it to pytest
PYTEST_ARGS=()
if [[ "$#" -gt 0 ]]; then
  if [[ "$1" == "--" ]]; then
    shift
    PYTEST_ARGS=("$@")
  fi
fi

# Load global.env defaults (scripts/run_with_env.sh is preferred in normal usage)
# But if you prefer this script, source the file if present
if [[ -f "/etc/justnews/global.env" ]]; then
  # shellcheck disable=SC1091
  source /etc/justnews/global.env
fi

export SKIP_PREFLIGHT=${SKIP_PREFLIGHT:-1}

case "$PRESET" in
  local)
    echo "Running local tests (defaults)"
    ;;
  gpu)
    echo "Enabling GPU tests (TEST_GPU_AVAILABLE=true)"
    export TEST_GPU_AVAILABLE=true
    ;;
  chroma-live)
    echo "Enabling live ChromaDB integration tests (ENABLE_CHROMADB_LIVE_TESTS=1)"
    export ENABLE_CHROMADB_LIVE_TESTS=1
    ;;
  vllm)
    echo "Enabling vLLM smoke tests (configure VLLM_BASE_URL / VLLM_API_KEY as required)"
    export VLLM_BASE_URL=${VLLM_BASE_URL:-http://127.0.0.1:7060/v1}
    ;;
  playwright)
    echo "Enabling Playwright UI tests (ENABLE_PLAYWRIGHT_TESTS=1)"
    export ENABLE_PLAYWRIGHT_TESTS=1
    ;;
  redis)
    echo "Enabling Redis-dependent tests (set REDIS_URL or use local Redis)"
    export REDIS_URL=${REDIS_URL:-redis://127.0.0.1:6379}
    # Indicate Docker available as many Redis-based E2E runs use containers
    export DOCKER_AVAILABLE=1
    ;;
  all)
    echo "Enabling all optional tests (GPU, Chroma live, Playwright, strict deprecations)"
    export TEST_GPU_AVAILABLE=true
    export ENABLE_CHROMADB_LIVE_TESTS=1
    export ENABLE_PLAYWRIGHT_TESTS=1
    export STRICT_PROTO_NO_DEPRECATION=1
    export DOCKER_AVAILABLE=1
    ;;
  *)
    echo "Unknown preset: $PRESET"
    echo "Usage: $0 [local|gpu|chroma-live|vllm|playwright|all] [-- pytest args...]"
    exit 2
    ;;
esac

# Print effective toggles for visibility
echo "Effective test toggles:"
env | grep -E 'TEST_GPU_AVAILABLE|ENABLE_CHROMADB_LIVE_TESTS|VLLM_BASE_URL|ENABLE_PLAYWRIGHT_TESTS|STRICT_PROTO_NO_DEPRECATION|DOCKER_AVAILABLE|CHROMADB_MODEL_SCOPED_COLLECTION' || true

echo "Running: pytest ${PYTEST_ARGS[*]} (SKIP_PREFLIGHT=${SKIP_PREFLIGHT})"
# Run pytest under the environment wrapper so global.env is applied consistently
scripts/run_with_env.sh pytest -q "${PYTEST_ARGS[@]}"
