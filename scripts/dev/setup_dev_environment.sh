#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_ENV_FILE="$REPO_ROOT/dev-environment.yml"
CANONICAL_ENV="${CANONICAL_ENV:-justnews-py312}"
DEV_ENV_NAME="${DEV_ENV_NAME:-${CANONICAL_ENV}-dev}"
EXISTING_ENV_NAME="${EXISTING_ENV_NAME:-${CANONICAL_ENV}}"

usage() {
  cat <<EOF
Usage: $0 [--create-dev] [--install-into-existing] [--create-all-phases] [--update-phases]

Options:
  --create-dev            Create a new development conda environment from
                          dev-environment.yml named "$DEV_ENV_NAME".

  --install-into-existing Install dev tooling into the existing environment
                          named "$EXISTING_ENV_NAME" (non-destructive).

  --create-all-phases     Create all 4 phased JustNews environments from
                          conda/environment.{base,phase1,phase2,phase3,phase4}.yml.

  --update-phases         Update existing phased environments (safe, non-destructive).

  --help                  Show this help message and exit.

Examples:
  # Create a dedicated dev environment (recommended):
  $0 --create-dev

  # Install tools into the existing runtime environment (careful):
  $0 --install-into-existing

  # Create all 4 workflow phase environments:
  $0 --create-all-phases

  # Update existing phase environments:
  $0 --update-phases
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
  # Apply vendor patches in this newly-created environment so third-party
  # packages that rely on legacy pkg_resources namespace helpers are patched
  # automatically and don't emit deprecation warnings at runtime.
  if command -v conda >/dev/null 2>&1; then
    echo "Applying vendor patch for google.rpc inside environment: $DEV_ENV_NAME"
    conda run -n "$DEV_ENV_NAME" --no-capture-output python scripts/vendor_patches/apply_google_rpc_namespace_patch.py || true
  fi
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
  # Also apply the vendor patch inside the target environment to avoid
  # runtime deprecation warnings for google.rpc after tool installation.
  if command -v conda >/dev/null 2>&1; then
    echo "Applying vendor patch for google.rpc inside environment: $EXISTING_ENV_NAME"
    conda run -n "$EXISTING_ENV_NAME" --no-capture-output python scripts/vendor_patches/apply_google_rpc_namespace_patch.py || true
  fi
  echo "Please run: conda activate $EXISTING_ENV_NAME and run pre-commit install in your repo to enable hooks"
}

create_phase_env() {
  local phase=$1
  require_conda
  INSTALLER=$(use_mamba_if_available)
  
  local phase_env_file="$REPO_ROOT/conda/environment.phase${phase}.yml"
  local phase_env_name="justnews-py312-phase${phase}"
  
  if [[ ! -f "$phase_env_file" ]]; then
    echo "❌ Phase $phase environment file not found: $phase_env_file" >&2
    return 1
  fi
  
  echo "📦 Creating Phase $phase environment: $phase_env_name"
  echo "   File: $phase_env_file"
  
  $INSTALLER env create -f "$phase_env_file" -n "$phase_env_name" || {
    echo "Create failed; trying to update if it already exists"
    $INSTALLER env update -f "$phase_env_file" -n "$phase_env_name"
  }
  
  echo "✅ Phase $phase environment created: $phase_env_name"
  
  # Apply vendor patches
  if command -v conda >/dev/null 2>&1; then
    echo "   Applying vendor patch for google.rpc..."
    conda run -n "$phase_env_name" --no-capture-output python scripts/vendor_patches/apply_google_rpc_namespace_patch.py || true
  fi
  
  return 0
}

create_all_phase_envs() {
  require_conda
  INSTALLER=$(use_mamba_if_available)
  echo "Using $INSTALLER"
  echo ""
  echo "📋 Creating all 4 JustNews phased environments..."
  echo ""
  
  local failed_phases=""
  
  for phase in 1 2 3 4; do
    if ! create_phase_env "$phase"; then
      failed_phases="${failed_phases} $phase"
    fi
    echo ""
  done
  
  if [[ -n "$failed_phases" ]]; then
    echo "❌ Failed to create phases:${failed_phases}" >&2
    return 1
  fi
  
  echo "✅ All phase environments created successfully!"
  echo ""
  echo "🎯 Next steps:"
  echo "   1. Select an active phase:"
  echo "      bash scripts/dev/select_phase_env.sh --phase 1"
  echo ""
  echo "   2. View all available phases:"
  echo "      bash scripts/dev/select_phase_env.sh --list-only"
  echo ""
  echo "   3. Run commands with the selected phase:"
  echo "      bash scripts/run_with_env.sh python -c 'import torch; print(torch.cuda.is_available())'"
  echo ""
  
  return 0
}

update_phase_envs() {
  require_conda
  INSTALLER=$(use_mamba_if_available)
  echo "Using $INSTALLER"
  echo ""
  echo "🔄 Updating all JustNews phased environments..."
  echo ""
  
  local failed_phases=""
  
  for phase in 1 2 3 4; do
    local phase_env_file="$REPO_ROOT/conda/environment.phase${phase}.yml"
    local phase_env_name="justnews-py312-phase${phase}"
    
    if [[ ! -f "$phase_env_file" ]]; then
      echo "⚠️  Phase $phase environment file not found: $phase_env_file"
      continue
    fi
    
    echo "🔄 Updating Phase $phase: $phase_env_name"
    
    if $INSTALLER env update -f "$phase_env_file" -n "$phase_env_name" 2>&1 | tail -3; then
      echo "✅ Phase $phase updated"
    else
      echo "❌ Phase $phase update failed"
      failed_phases="${failed_phases} $phase"
    fi
    echo ""
  done
  
  if [[ -n "$failed_phases" ]]; then
    echo "⚠️  Some phases had update issues:${failed_phases}" >&2
    echo "   You may need to recreate these environments with --create-all-phases"
    return 1
  fi
  
  echo "✅ All phase environments updated successfully!"
  return 0
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
    --create-all-phases)
      create_all_phase_envs
      shift
      ;;
    --update-phases)
      update_phase_envs
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
