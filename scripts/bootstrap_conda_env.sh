#!/usr/bin/env bash
# Idempotent conda env bootstrap for JustNews canonical environment
# Usage: ./scripts/bootstrap_conda_env.sh [--force] [--install-vllm-only] [--skip-vllm]
# - --force : remove and recreate env
# - --install-vllm-only : don't update environment.yml, only ensure vllm is installed
# - --skip-vllm : create/update env but do not install vllm

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_NAME=${ENV_NAME:-${CANONICAL_ENV:-justnews-py312-phase1}}
ENV_YML="${ENV_YML:-}"
REQS="$ROOT_DIR/requirements.txt"
FORCE=0
INSTALL_VLLM_ONLY=0
SKIP_VLLM=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1; shift ;;
    --install-vllm-only) INSTALL_VLLM_ONLY=1; shift ;;
    --skip-vllm) SKIP_VLLM=1; shift ;;
    -h|--help) echo "Usage: $0 [--force] [--install-vllm-only] [--skip-vllm]"; exit 0 ;;
    *) echo "Unknown arg: $arg"; exit 2 ;;
  esac
done

if [[ -z "$ENV_YML" ]]; then
  case "$ENV_NAME" in
    *-phase1) ENV_YML="$ROOT_DIR/conda/environment.phase1.yml" ;;
    *-phase2) ENV_YML="$ROOT_DIR/conda/environment.phase2.yml" ;;
    *-phase3) ENV_YML="$ROOT_DIR/conda/environment.phase3.yml" ;;
    *-phase4) ENV_YML="$ROOT_DIR/conda/environment.phase4.yml" ;;
    *) ENV_YML="$ROOT_DIR/environment.yml" ;;
  esac
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "Error: conda not found in PATH. Install Miniconda/Anaconda and retry." >&2
  exit 1
fi

env_exists=0
if conda env list | awk '{print $1}' | grep -xq "^${ENV_NAME}$"; then
  env_exists=1
fi

if [ "$FORCE" -eq 1 ] && [ "$env_exists" -eq 1 ]; then
  echo "Removing existing environment ${ENV_NAME} (--force requested)"
  conda env remove -n "${ENV_NAME}" -y
  env_exists=0
fi

if [ "$INSTALL_VLLM_ONLY" -eq 1 ]; then
  echo "Installing vLLM into existing or new ${ENV_NAME} (install-vllm-only)"
  if [ "$env_exists" -eq 0 ]; then
    echo "Environment ${ENV_NAME} does not exist; creating minimal env"
    conda create -y -n "${ENV_NAME}" python=3.12
  fi
else
  if [ -f "$ENV_YML" ]; then
    if [ "$env_exists" -eq 0 ]; then
      echo "Creating conda environment ${ENV_NAME} from ${ENV_YML}"
      conda env create -n "${ENV_NAME}" -f "$ENV_YML" || (
        echo "Failed to create from ${ENV_YML}; attempting update" ; conda env update -n "${ENV_NAME}" -f "$ENV_YML" --prune || true
      )
    else
      echo "Updating existing environment ${ENV_NAME} from ${ENV_YML}"
      conda env update -n "${ENV_NAME}" -f "$ENV_YML" --prune || true
    fi
  else
    if [ "$env_exists" -eq 0 ]; then
      echo "No environment.yml found: creating minimal conda env ${ENV_NAME}"
      conda create -y -n "${ENV_NAME}" python=3.12
      if [ -f "$REQS" ]; then
        echo "Installing requirements.txt via pip inside ${ENV_NAME}"
        conda run -n "${ENV_NAME}" python -m pip install --upgrade pip
        conda run -n "${ENV_NAME}" python -m pip install -r "$REQS"
      fi
    else
      echo "Environment ${ENV_NAME} exists; skipping creation"
    fi
  fi
fi

if [ "$SKIP_VLLM" -eq 1 ]; then
  echo "SKIP_VLLM set: skipping vLLM installation"
  exit 0
fi

# Install vLLM into the env (server extras)
# Prefer installing via pip in the conda env for latest release
echo "Ensuring vLLM (server extras) is installed in ${ENV_NAME}"
conda run -n "${ENV_NAME}" python -m pip install --upgrade pip setuptools wheel
# vllm server extra is sufficient; avoid expensive extras by default
conda run -n "${ENV_NAME}" python -m pip install -U "vllm[server]" || (
  echo "Failed to install vllm[server] via pip; attempting vllm without extras" ; conda run -n "${ENV_NAME}" python -m pip install -U vllm
)

# Optional: verify vllm binary works
if conda run -n "${ENV_NAME}" bash -lc "command -v vllm >/dev/null 2>&1"; then
  echo "vllm installed successfully in ${ENV_NAME}"
else
  echo "Warning: vllm command not found in ${ENV_NAME} (check pip install output)" >&2
fi

# Post-install instructions
cat <<'EOF'

Bootstrap complete.
To use the environment interactively:
  conda activate ${CANONICAL_ENV:-justnews-py312-phase1}
To run repository scripts with canonical env:
  ./scripts/run_with_env.sh <command>

If you installed vLLM, you can now install the systemd unit and start the service:
  make vllm-install-and-start

EOF
