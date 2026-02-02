#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_ENV_FILE="$REPO_ROOT/dev-environment.yml"
CANONICAL_ENV="${CANONICAL_ENV:-justnews-py312-phase1}"
DEV_ENV_NAME="${DEV_ENV_NAME:-${CANONICAL_ENV}-dev}"
EXISTING_ENV_NAME="${EXISTING_ENV_NAME:-${CANONICAL_ENV}}"

usage() {
  cat <<EOF
Usage: $0 [--create-dev] [--install-into-existing]

Options:
  --create-dev            Create a new development conda environment from
                          dev-environment.yml named "$DEV_ENV_NAME".

  --install-into-existing Install dev tooling into the existing environment
                          named "$EXISTING_ENV_NAME" (non-destructive).

  --help                  Show this help message and exit.

Examples:
  # Create a dedicated dev environment (recommended):
  $0 --create-dev

  # Install tools into the existing runtime environment (careful):
  $0 --install-into-existing
EOF
}

require_conda() {
  if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda is not available in PATH. Please install miniconda/conda or use mamba." >&2
    exit 2
  fi
}

use_mamba_if_available() {
  if command -v mamba >/dev/null 2>&1; then
    # Return only the command name so callers can execute it directly
    echo "mamba"
  else
    echo "conda"
  fi
}

create_dev_env() {
  require_conda
  INSTALLER=$(use_mamba_if_available)
  echo "Using $INSTALLER"
  echo "Creating dev environment '$DEV_ENV_NAME' from $DEV_ENV_FILE"
  if [ ! -f "$DEV_ENV_FILE" ]; then
    echo "ERROR: $DEV_ENV_FILE not found" >&2
    exit 3
  fi
  $INSTALLER env create -f "$DEV_ENV_FILE" -n "$DEV_ENV_NAME" || {
    echo "Create failed; trying to update if it already exists"
    $INSTALLER env update -f "$DEV_ENV_FILE" -n "$DEV_ENV_NAME"
  }
  echo "Dev environment created: $DEV_ENV_NAME"
}

install_into_existing() {
  require_conda
  INSTALLER=$(use_mamba_if_available)
  echo "Using $INSTALLER"
  echo "Installing dev tools into existing environment: $EXISTING_ENV_NAME"

  # Export a snapshot so changes can be rolled back if needed.
  snapshot="$REPO_ROOT/env-snapshot-before-devtools.yml"
  echo "Exporting current env to $snapshot"
  conda env export -n "$EXISTING_ENV_NAME" > "$snapshot" || true

  echo "Installing packages (non-destructive): ruff, isort, black, pre-commit"
  $INSTALLER install -n "$EXISTING_ENV_NAME" -c conda-forge ruff isort black pre-commit || {
    echo "Fallback to conda install failed; attempting pip install inside env"
    # Best-effort pip install inside environment
    # Note: conda run is used to run pip in the target env
    conda run -n "$EXISTING_ENV_NAME" --no-capture-output python -m pip install --upgrade ruff isort black pre-commit
  }
  echo "Dev tools installed into $EXISTING_ENV_NAME"
  echo "Please run: conda activate $EXISTING_ENV_NAME and run pre-commit install in your repo to enable hooks"
}

if [ $# -eq 0 ]; then
  usage
  exit 1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --create-dev)
      create_dev_env
      shift
      ;;
    --install-into-existing)
      install_into_existing
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done
