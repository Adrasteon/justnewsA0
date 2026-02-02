#!/usr/bin/env bash
set -euo pipefail

# Lightweight soak runner for GPU orchestrator workloads using the repo perf helper.
# Intended to be run on a GPU-capable host (self-hosted CI runner or staging host).
# Example: ./scripts/perf/orchestrator_soak.sh --requests 40 --sweep --model mistralai/Mistral-7B-Instruct-v0.3

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
CANONICAL_ENV=${CANONICAL_ENV:-justnews-py312-phase3}

REQUESTS=20
SWEEP=0
SWEEP_MAX=2
MODEL=${MODEL:-mistralai/Mistral-7B-Instruct-v0.3}

while [[ $# -gt 0 ]]; do
  case $1 in
    --requests) REQUESTS="$2"; shift 2 ;;
    --sweep) SWEEP=1; shift ;;
    --sweep-max) SWEEP_MAX="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 [--requests N] [--sweep] [--sweep-max N] [--model MODEL]"; exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

OUT_DIR="$REPO_ROOT/scripts/perf/results"
mkdir -p "$OUT_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT_CSV="$OUT_DIR/orchestrator-soak-${TS}.csv"

echo "Running orchestrator soak: requests=$REQUESTS sweep=$SWEEP model=$MODEL"

# Run using canonical env wrapper if present
if [[ -x "$REPO_ROOT/scripts/run_with_env.sh" ]]; then
  WRAPPER="$REPO_ROOT/scripts/run_with_env.sh"
else
  WRAPPER=""
fi

CMD="$WRAPPER conda run -n ${CANONICAL_ENV} python $REPO_ROOT/scripts/perf/simulate_concurrent_inference.py --requests ${REQUESTS}"
if [[ $SWEEP -eq 1 ]]; then
  CMD="$CMD --sweep --sweep-max ${SWEEP_MAX}"
fi
CMD="$CMD --model ${MODEL} --output-csv ${OUT_CSV}"

echo "Executing: $CMD"
eval "$CMD"

echo "Results -> ${OUT_CSV}"
