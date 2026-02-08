#!/usr/bin/env bash
set -euo pipefail

# This script validates that the repository does not contain non-canonical
# conda environment names in source or config files. We allow legacy names
# in logs and artifacts (historical); those are excluded from the scan.

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$(pwd)")
echo "Checking repository for non-canonical conda env names..."

CANONICAL_ENV="${CANONICAL_ENV:-justnews-py312}"

# Patterns we don't want to see in source/config — legacy names that must be
# replaced with the project's canonical environment name above.
PATTERNS=(
  # Common variants we don't want to remain as hard-coded strings
  "justnews-py312"
  "justnews-py312-dev"
  "justnews-v2-py312"
  "justnews-v2-py312-fix"
)

EXCLUDES=(
  --exclude-dir=.git
  --exclude-dir=logs
  --exclude-dir=artifacts
  --exclude-dir=docs
  --exclude-dir=.mypy_cache
  --exclude-dir=__pycache__
)

# Also ignore this script file (it contains the patterns for detection)
IGNORED_FILES=(
  ':!scripts/dev/check_canonical_env.sh'
)

failures=0
for pat in "${PATTERNS[@]}"; do
  echo "Searching for $pat (excluding logs/artifacts)..."
  # Use git grep when available (faster/accurate), fall back to grep -R
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # Use git grep and explicitly exclude logs/artifacts and this script file
    matches=$(git grep -n --untracked -I -e "$pat" -- ':!logs' ':!artifacts' ':!docs' "${IGNORED_FILES[@]}" || true)
  else
    matches=$(grep -R --line-number -I "$pat" . ${EXCLUDES[*]} | grep -v "scripts/dev/check_canonical_env.sh" || true)
  fi

  if [[ -n "$matches" ]]; then
    # Filter out occurrences that are legitimate uses of CANONICAL_ENV or
    # those that intentionally set/declare the canonical variable. We want to
    # catch *raw* literal usages like 'conda run -n justnews-py312' or
    # 'conda activate justnews-py312' in source or docs.
    # Ignore any legitimate uses that reference the CANONICAL_ENV variable
    filtered=$(echo "$matches" | grep -v -E "(\$\{CANONICAL_ENV|CANONICAL_ENV)" || true)
    # Also exclude matches within our configured exclusion directories
    filtered=$(echo "$filtered" | grep -v -E "(^.*/(logs|artifacts)/)" || true)
    # Ignore canonical environment specification files (environment.yml) which
    # purposely contain the canonical env name as the env manifest name.
    filtered=$(echo "$filtered" | grep -v -E "(^|/)(environment.yml)(:|$)" || true)

    if [[ -n "$filtered" ]]; then
      echo "Found raw occurrences of $pat in source/config (these should be replaced to use \\$\{CANONICAL_ENV:-${CANONICAL_ENV}} or similar):"
      echo "$filtered"
      failures=1
    fi
  fi
done

if [[ $failures -ne 0 ]]; then
  echo "ERROR: Non-canonical conda env names found in source/config files. Please replace them with '${CANONICAL_ENV}'."
  exit 1
fi

echo "OK — no non-canonical conda env names found in source/config files."
exit 0
