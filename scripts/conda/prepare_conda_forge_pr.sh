#!/usr/bin/env bash
set -euo pipefail

RECIPE_DIR="conda/recipes/protobuf"
BRANCH="add-protobuf-recipe-$(date +%Y%m%d%H%M%S)"

if [[ ! -d "$RECIPE_DIR" ]]; then
  echo "ERROR: recipe directory not found: $RECIPE_DIR" >&2
  exit 2
fi

echo "Preparing a branch with recipe for conda-forge staged-recipes..."
git checkout -b "$BRANCH"
git add "$RECIPE_DIR"
git commit -m "chore(conda): add protobuf recipe for possible conda-forge staged-recipes PR"

echo "Created branch: $BRANCH" 
echo "Next steps: push the branch and open a PR against conda-forge/staged-recipes."
echo "  git push origin $BRANCH"
echo "  Open a PR via GitHub UI targetting conda-forge/staged-recipes and include the recipe path: $RECIPE_DIR"
