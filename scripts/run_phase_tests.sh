#!/bin/bash
# Run pytest suite partitioned by workflow phase
# Each phase runs in its own conda environment with phase-specific test markers
#
# Usage:
#   ./scripts/run_phase_tests.sh 1              # Run phase1 tests
#   ./scripts/run_phase_tests.sh all            # Run all phases (sequential)
#   ./scripts/run_phase_tests.sh all --parallel # Run all phases (parallel)
#   ./scripts/run_phase_tests.sh 1 -v           # Run phase1 with verbose output

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Phased environments and their test markers
declare -A PHASE_ENV=(
    [1]="justnews-py312-phase1"
    [2]="justnews-py312-phase2"
    [3]="justnews-py312-phase3"
    [4]="justnews-py312-phase4"
)

declare -A PHASE_MARKS=(
    [1]="phase1 or (not phase2 and not phase3 and not phase4 and not integration and not slow)"
    [2]="phase2 or (not phase1 and not phase3 and not phase4 and not integration and not slow)"
    [3]="phase3 or (not phase1 and not phase2 and not phase4 and not integration and not slow)"
    [4]="phase4 or (not phase1 and not phase2 and not phase3 and not integration and not slow)"
)

declare -A PHASE_DESCRIPTION=(
    [1]="GPU Ingestion, Embedding, Crawler (Phase 1)"
    [2]="CPU Clustering, Analytics, DB, Unit tests (Phase 2)"
    [3]="GPU Synthesis, LLM Inference, Model Adapters (Phase 3)"
    [4]="CPU Publishing, Django, Web Stack (Phase 4)"
)

PHASE="${1:-all}"
PARALLEL_MODE=false
PYTEST_ARGS=""

# Parse additional arguments
shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --parallel)
            PARALLEL_MODE=true
            shift
            ;;
        --verbose|-v)
            PYTEST_ARGS="$PYTEST_ARGS -vv"
            shift
            ;;
        --strict|-x)
            PYTEST_ARGS="$PYTEST_ARGS -x"
            shift
            ;;
        --collect-only|-q)
            PYTEST_ARGS="$PYTEST_ARGS --collect-only"
            shift
            ;;
        *)
            PYTEST_ARGS="$PYTEST_ARGS $1"
            shift
            ;;
    esac
done

run_phase() {
    local phase=$1
    local env=${PHASE_ENV[$phase]}
    local marker="${PHASE_MARKS[$phase]}"
    local desc="${PHASE_DESCRIPTION[$phase]}"
    
    if [ -z "$env" ]; then
        echo "Error: Unknown phase '$phase'" >&2
        return 1
    fi
    
    echo ""
    echo "=========================================="
    echo "Phase $phase: $desc"
    echo "Environment: $env"
    echo "=========================================="
    
    if ! conda env list | grep -q "^${env} "; then
        echo "Error: Environment $env not found. Run: conda env list" >&2
        return 1
    fi
    
    # Run pytest with phase-specific markers
    conda run -n "$env" pytest tests/ \
        -m "$marker" \
        --tb=short \
        --durations=10 \
        $PYTEST_ARGS
    
    # Capture exit code but continue for parallel mode
    local exit_code=$?
    if [ $exit_code -ne 0 ] && [ "$PARALLEL_MODE" = false ]; then
        echo "⚠️  Phase $phase tests failed (exit code: $exit_code)"
        return $exit_code
    fi
    
    return 0
}

# Main execution
case "$PHASE" in
    all)
        echo "Running full phased test suite..."
        
        if [ "$PARALLEL_MODE" = true ]; then
            echo "Parallel mode: Running phases concurrently (requires multiple terminals in practice)"
            # In a real scenario, you'd use GNU parallel or similar. For now, sequential:
            for phase in 1 2 3 4; do
                run_phase $phase || true
            done
        else
            echo "Sequential mode: Running phases one at a time..."
            for phase in 1 2 3 4; do
                run_phase $phase || true
            done
        fi
        ;;
    1|2|3|4)
        run_phase "$PHASE"
        ;;
    *)
        echo "Usage: $0 {1|2|3|4|all} [--parallel] [-v|--verbose] [-x|--strict] [--collect-only] [additional pytest args]"
        echo ""
        echo "Phases:"
        echo "  1  Phase 1 (GPU Ingestion, Embeddings, Crawler)"
        echo "  2  Phase 2 (CPU Clustering, Analytics, Unit Tests)"
        echo "  3  Phase 3 (GPU Synthesis, LLM Inference)"
        echo "  4  Phase 4 (CPU Publishing, Django)"
        echo "  all Run all phases sequentially (or --parallel)"
        echo ""
        echo "Options:"
        echo "  --parallel      Run phases in parallel (requires background jobs)"
        echo "  -v, --verbose   Verbose pytest output"
        echo "  -x, --strict    Stop on first failure"
        echo "  --collect-only  Discover tests without running them"
        exit 1
        ;;
esac
