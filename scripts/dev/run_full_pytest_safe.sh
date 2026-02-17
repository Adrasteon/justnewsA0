#!/usr/bin/env bash
set -euo pipefail

# Run the full pytest suite in the canonical conda environment with safe defaults
# that avoid real GPU usage on developer machines.

export TEST_GPU_AVAILABLE=${TEST_GPU_AVAILABLE:-false}
export TEST_GPU_COUNT=${TEST_GPU_COUNT:-0}
export USE_REAL_ML_LIBS=${USE_REAL_ML_LIBS:-0}
export SAFE_MODE=${SAFE_MODE:-true}

echo "Running pytest with the following safe env settings:" 
echo "  TEST_GPU_AVAILABLE=$TEST_GPU_AVAILABLE"
echo "  TEST_GPU_COUNT=$TEST_GPU_COUNT"
echo "  USE_REAL_ML_LIBS=$USE_REAL_ML_LIBS"
echo "  SAFE_MODE=$SAFE_MODE"

exec ./scripts/dev/pytest.sh "$@"
