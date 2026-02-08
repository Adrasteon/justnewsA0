#!/usr/bin/env bash
# Install repository git hooks from scripts/dev/git-hooks into .git/hooks

set -euo pipefail

HOOK_DIR=".git/hooks"
SRC_DIR="scripts/dev/git-hooks"

if [ ! -d ".git" ]; then
  echo "No .git directory found; are you in the repository root?" >&2
  exit 2
fi

echo "Installing git hooks from ${SRC_DIR} to ${HOOK_DIR} (overwrites existing hooks with the same name)."
mkdir -p ${HOOK_DIR}
for f in ${SRC_DIR}/*; do
  fname=$(basename "$f")
  dst=${HOOK_DIR}/$fname
  echo "Installing $fname -> $dst"
  cp "$f" "$dst"
  chmod +x "$dst"
done

echo "Done. To make the pre-push hook run strict tests, set GIT_STRICT_TEST_HOOK=1 in your environment."
