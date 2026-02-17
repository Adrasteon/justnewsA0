#!/usr/bin/env bash
set -euo pipefail

# Phase Selection Script for JustNews Phased Environments
# 
# Usage:
#   ./scripts/dev/select_phase_env.sh --phase 1
#   ./scripts/dev/select_phase_env.sh --phase 3 --list-only
#
# This script:
# 1. Validates that a phased conda environment exists
# 2. Updates global.env with CANONICAL_ENV and PYTHON_BIN for the selected phase
# 3. Outputs helpful verification commands

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GLOBAL_ENV="${REPO_ROOT}/global.env"
CONDA_PREFIX="${CONDA_PREFIX:-${HOME}/miniconda3}"

# Default phase
SELECTED_PHASE=""
LIST_ONLY=false
VERIFY_ONLY=false

usage() {
  cat <<EOF
Usage: $0 --phase <1|2|3|4> [--list-only] [--verify]

Options:
  --phase <1|2|3|4>      Select workflow phase environment (required)
  --list-only           List available phase envs without switching (default: false)
  --verify              Check if selected phase env exists (default: false)
  --help                Show this help message

Examples:
  # Select Phase 1 (Ingestion & Vectorization)
  $0 --phase 1

  # List all available phase environments
  $0 --list-only

  # Just verify Phase 3 exists without switching
  $0 --phase 3 --verify

Environment Variables:
  CONDA_PREFIX          Conda installation directory (default: ~/miniconda3)
  CANONICAL_ENV         Currently active env name (will be updated)
  PYTHON_BIN            Python binary path (will be updated)

EOF
}

require_conda() {
  if ! command -v conda >/dev/null 2>&1; then
    echo "❌ ERROR: conda is not available in PATH. Please install miniconda/conda or use mamba." >&2
    exit 2
  fi
}

use_mamba_if_available() {
  if command -v mamba >/dev/null 2>&1; then
    echo "mamba"
  else
    echo "conda"
  fi
}

get_env_path() {
  local phase=$1
  local env_name="justnews-py312-phase${phase}"
  echo "${CONDA_PREFIX}/envs/${env_name}"
}

env_exists() {
  local phase=$1
  local env_path
  env_path=$(get_env_path "$phase")
  [[ -d "${env_path}" ]]
}

list_phase_envs() {
  echo "📋 Available JustNews phase environments:"
  echo ""
  
  for phase in 1 2 3 4; do
    env_path=$(get_env_path "$phase")
    if env_exists "$phase"; then
      python_bin="${env_path}/bin/python"
      if [[ -x "${python_bin}" ]]; then
        version=$("${python_bin}" --version 2>&1 | awk '{print $2}')
        echo "  ✅ Phase $phase (justnews-py312-phase${phase})"
        echo "     Path: ${env_path}"
        echo "     Python: ${version}"
        
        # Check for GPU deps in Phase 1 & 3
        if [[ $phase == "1" || $phase == "3" ]]; then
          if "${python_bin}" -c "import torch" 2>/dev/null; then
            echo "     GPU: ✅ torch available"
          else
            echo "     GPU: ❌ torch NOT available"
          fi
        fi
      fi
    else
      echo "  ❌ Phase $phase (NOT FOUND: justnews-py312-phase${phase})"
      echo "     Run: conda env create -f ${REPO_ROOT}/conda/environment.phase${phase}.yml"
    fi
    echo ""
  done
}

verify_phase() {
  local phase=$1
  local env_path
  env_path=$(get_env_path "$phase")
  
  if ! env_exists "$phase"; then
    echo "❌ Phase $phase environment does not exist at ${env_path}" >&2
    echo "   Create it with: conda env create -f ${REPO_ROOT}/conda/environment.phase${phase}.yml" >&2
    return 1
  fi
  
  local python_bin="${env_path}/bin/python"
  if [[ ! -x "${python_bin}" ]]; then
    echo "❌ Python binary not found or not executable: ${python_bin}" >&2
    return 1
  fi
  
  echo "✅ Phase $phase environment verified"
  echo "   Env: justnews-py312-phase${phase}"
  echo "   Path: ${env_path}"
  echo "   Python: $(${python_bin} --version 2>&1)"
  
  return 0
}

select_phase() {
  local phase=$1
  require_conda
  
  if ! env_exists "$phase"; then
    echo "❌ Phase $phase environment not found!" >&2
    echo "" >&2
    echo "Create it first with:" >&2
    echo "  conda env create -f ${REPO_ROOT}/conda/environment.phase${phase}.yml -n justnews-py312-phase${phase}" >&2
    echo "" >&2
    echo "Or create all phases with:" >&2
    echo "  bash ${REPO_ROOT}/scripts/dev/setup_dev_environment.sh --create-all-phases" >&2
    exit 1
  fi
  
  # Get paths
  local env_path env_name python_bin
  env_path=$(get_env_path "$phase")
  env_name="justnews-py312-phase${phase}"
  python_bin="${env_path}/bin/python"
  
  # Validate python binary
  if [[ ! -x "${python_bin}" ]]; then
    echo "❌ Python binary not found or not executable: ${python_bin}" >&2
    exit 1
  fi
  
  # Update global.env with new phase env vars
  if [[ ! -f "${GLOBAL_ENV}" ]]; then
    echo "❌ ${GLOBAL_ENV} not found. Please create it from global.env.sample" >&2
    exit 1
  fi
  
  # Create backup
  local backup_env="${GLOBAL_ENV}.backup.$(date +%s)"
  cp "${GLOBAL_ENV}" "${backup_env}"
  echo "📦 Backup created: ${backup_env}"
  
  # Update CANONICAL_ENV
  if grep -q "^CANONICAL_ENV=" "${GLOBAL_ENV}"; then
    sed -i "s|^CANONICAL_ENV=.*|CANONICAL_ENV=${env_name}|" "${GLOBAL_ENV}"
  else
    echo "CANONICAL_ENV=${env_name}" >> "${GLOBAL_ENV}"
  fi
  
  # Update PYTHON_BIN
  if grep -q "^PYTHON_BIN=" "${GLOBAL_ENV}"; then
    sed -i "s|^PYTHON_BIN=.*|PYTHON_BIN=${python_bin}|" "${GLOBAL_ENV}"
  else
    echo "PYTHON_BIN=${python_bin}" >> "${GLOBAL_ENV}"
  fi
  
  # Update JUSTNEWS_PYTHON (alias for PYTHON_BIN)
  if grep -q "^JUSTNEWS_PYTHON=" "${GLOBAL_ENV}"; then
    sed -i "s|^JUSTNEWS_PYTHON=.*|JUSTNEWS_PYTHON=${python_bin}|" "${GLOBAL_ENV}"
  else
    echo "JUSTNEWS_PYTHON=${python_bin}" >> "${GLOBAL_ENV}"
  fi
  
  # Update CANONICAL_PYTHON_PATH (alias for PYTHON_BIN)
  if grep -q "^CANONICAL_PYTHON_PATH=" "${GLOBAL_ENV}"; then
    sed -i "s|^CANONICAL_PYTHON_PATH=.*|CANONICAL_PYTHON_PATH=${python_bin}|" "${GLOBAL_ENV}"
  else
    echo "CANONICAL_PYTHON_PATH=${python_bin}" >> "${GLOBAL_ENV}"
  fi
  
  # Update CONDA_PREFIX
  if grep -q "^CONDA_PREFIX=" "${GLOBAL_ENV}"; then
    sed -i "s|^CONDA_PREFIX=.*|CONDA_PREFIX=${env_path}|" "${GLOBAL_ENV}"
  else
    echo "CONDA_PREFIX=${env_path}" >> "${GLOBAL_ENV}"
  fi
  
  cat <<EOF

✅ Phase $phase ($env_name) selected successfully!

📝 Updated in ${GLOBAL_ENV}:
   CANONICAL_ENV=${env_name}
   PYTHON_BIN=${python_bin}
   CONDA_PREFIX=${env_path}

🔍 Verification:
   # Verify environment was switched
   source ${GLOBAL_ENV}
   which python
   python --version
   
   # Run a command with the selected env
   bash ${REPO_ROOT}/scripts/run_with_env.sh python -c "import sys; print(sys.prefix)"

📌 Phase Description:
EOF
  
  case "$phase" in
    1)
      cat <<EOF
   Phase 1: Ingestion & Vectorization (GPU-enabled)
   - Agents: crawler, memory (embeddings)
   - Dependencies: PyTorch, sentence-transformers, crawl4ai
   - Use when: Running crawler and embedding jobs
EOF
      ;;
    2)
      cat <<EOF
   Phase 2: Clustering & Linkage (CPU-only)
   - Agents: memory (ChromaDB), clustering logic
   - Dependencies: hdbscan, umap (NO GPU)
   - Use when: Running clustering and discovery jobs
EOF
      ;;
    3)
      cat <<EOF
   Phase 3: Synthesis & Curation (GPU-enabled)
   - Agents: synthesizer, critic, analyst
   - Dependencies: vLLM, transformers, bitsandbytes
   - Use when: Running LLM synthesis and criticism jobs
EOF
      ;;
    4)
      cat <<EOF
   Phase 4: Publication & CMS Push (CPU-only)
   - Agents: chief_editor, journalist
   - Dependencies: (minimal, no GPU)
   - Use when: Publishing and pushing to CMS
EOF
      ;;
  esac
  
  echo ""
  echo "💡 Tip: To switch phases, run this script again with a different --phase number"
  echo ""
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase)
      SELECTED_PHASE="$2"
      shift 2
      ;;
    --list-only)
      LIST_ONLY=true
      shift
      ;;
    --verify)
      VERIFY_ONLY=true
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "❌ Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

# Main logic
if [[ "$LIST_ONLY" == "true" ]]; then
  require_conda
  list_phase_envs
  exit 0
fi

if [[ -z "$SELECTED_PHASE" ]]; then
  echo "❌ --phase argument is required" >&2
  usage
  exit 1
fi

# Validate phase number
if ! [[ "$SELECTED_PHASE" =~ ^[1234]$ ]]; then
  echo "❌ Invalid phase: $SELECTED_PHASE. Must be 1, 2, 3, or 4" >&2
  usage
  exit 1
fi

if [[ "$VERIFY_ONLY" == "true" ]]; then
  verify_phase "$SELECTED_PHASE"
  exit $?
fi

select_phase "$SELECTED_PHASE"
