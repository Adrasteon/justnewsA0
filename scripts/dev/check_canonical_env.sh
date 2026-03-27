#!/usr/bin/env bash
set -euo pipefail

# Validate that repository runtime references are aligned to UV/venv and do not
# hard-code legacy JustNews conda env names in active source/config paths.

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$(pwd)")
cd "$ROOT"

echo "Checking repository for legacy conda env literals..."

PATTERNS=(
  "justnews-py312"
  "justnews-py312-dev"
  "justnews-v2-py312"
  "justnews-v2-py312-fix"
)

# Allow references in archival/deprecation materials while enforcing active runtime paths.
ALLOW_PATHS_REGEX='^(archive_local/|docs/|CHANGELOG\.md$|PHASED_ENVIRONMENT_ROLLOUT_PLAN\.md$|QUICK_REFERENCE_CARD\.md$|PROJECT_INDEX\.md$|infrastructure/.*\.md$|scripts/dev/check_canonical_env\.sh$|tests/test_check_canonical_env\.py$|train_qlora/README\.md$|agents/hitl_service/README\.md$|requirements\.txt$|\.gitignore$|tests/.*$|conftest\.py$|scripts/dev/setup_dev_environment\.sh$|scripts/setup_dev_environment\.sh$|infrastructure/systemd/preflight\.sh$|infrastructure/systemd/canonical_system_startup\.sh$)'

failures=0
for pat in "${PATTERNS[@]}"; do
  matches=$(git grep -n --untracked -I -e "$pat" -- . || true)
  if [[ -z "$matches" ]]; then
    continue
  fi

  filtered=$(echo "$matches" | awk -F: -v re="$ALLOW_PATHS_REGEX" '$1 !~ re')
  if [[ -n "$filtered" ]]; then
    echo "Found disallowed raw occurrences of '$pat':"
    echo "$filtered"
    failures=1
  fi
done

if [[ $failures -ne 0 ]]; then
  echo "ERROR: legacy conda env literals found in active files."
  exit 1
fi

echo "OK — no legacy conda env literals found in active source/config files."
exit 0
