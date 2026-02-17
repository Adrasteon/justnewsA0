#!/usr/bin/env bash
# Run pytest using the canonical project conda environment when available
set -euo pipefail

CANONICAL_ENV="${CANONICAL_ENV:-justnews-py312}"

if command -v conda >/dev/null 2>&1; then
    # If the environment exists, run tests inside it
    if conda env list 2>/dev/null | awk '{print $1}' | grep -xq "$CANONICAL_ENV"; then
        echo "Running pytest inside conda env: $CANONICAL_ENV"
        # If no pytest args were provided, detect interactive TTY sessions and
        # show per-test names (-vv) for better progress visibility. In CI or
        # non-interactive environments we stay quiet with -q to reduce log noise.
        if [ "$#" -eq 0 ]; then
            if [ -t 1 ] && [ "${CI:-}" != "true" ]; then
                PYTEST_ARGS=("-vv")
            else
                PYTEST_ARGS=("-q")
            fi
        else
            PYTEST_ARGS=("$@")
        fi
        conda run -n "$CANONICAL_ENV" pytest "${PYTEST_ARGS[@]}"
        exit $?
    fi
fi

# If we reach here no canonical conda env was found. Require it by default
# unless user explicitly allows any pytest environment via ALLOW_ANY_PYTEST_ENV.
if [[ "${ALLOW_ANY_PYTEST_ENV:-}" == "1" ]]; then
    if command -v pytest >/dev/null 2>&1; then
        echo "ALLOW_ANY_PYTEST_ENV=1 set; falling back to system pytest"
        pytest "$@"
        exit $?
    fi
    echo "ERROR: ALLOW_ANY_PYTEST_ENV=1 but pytest is not installed on this system."
    exit 2
fi

echo "ERROR: conda env '$CANONICAL_ENV' not found. Tests must run inside the canonical conda env by default."
echo "Create it (environment.yml) or set ALLOW_ANY_PYTEST_ENV=1 to override (not recommended)."
exit 2
