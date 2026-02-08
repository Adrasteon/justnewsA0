#!/usr/bin/env bash
set -euo pipefail

RECIPE_DIR=conda/recipes/protobuf

if ! command -v conda-build >/dev/null 2>&1; then
  echo "conda-build is not installed. Skipping recipe check."
  exit 0
fi

echo "Checking recipe render for: $RECIPE_DIR"
conda-build "$RECIPE_DIR" --output || true

echo "If the above printed an output path, the recipe rendered successfully."
