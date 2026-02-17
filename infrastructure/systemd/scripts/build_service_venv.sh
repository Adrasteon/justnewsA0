#!/usr/bin/env bash
# Deterministic venv builder for JustNews V4 Preview workspace
# Creates a reproducible Python virtual environment for production deployments
#
# Usage:
#   build_service_venv.sh --venv /opt/justnews/venv --requirements release_beta_minimal_preview/requirements-runtime.txt
#   build_service_venv.sh --venv /opt/justnews/venv --requirements requirements.txt --full
#
# Options:
#   --venv PATH           Target venv directory (required)
#   --requirements FILE   Requirements file to install (required)
#   --full                Install full development dependencies (default: runtime only)
#   --python CMD          Python command to use (default: python3)
#   --verify              Run post-install verification (default: enabled)
#   --no-verify           Skip post-install verification
#   -h, --help            Show this help message

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Default values
VENV_PATH=""
REQUIREMENTS_FILE=""
PYTHON_CMD="python3"
VERIFY=true
FULL_INSTALL=false

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

show_help() {
    cat << EOF
Deterministic venv builder for JustNews V4

Usage: $0 [OPTIONS]

Required:
  --venv PATH           Target venv directory
  --requirements FILE   Requirements file to install

Options:
  --full                Install full development dependencies
  --python CMD          Python command to use (default: python3)
  --verify              Run post-install verification (default)
  --no-verify           Skip post-install verification
  -h, --help            Show this help message

Examples:
  # Production runtime environment:
  $0 --venv /opt/justnews/venv --requirements release_beta_minimal_preview/requirements-runtime.txt

  # Development environment with full dependencies:
  $0 --venv .venv --requirements requirements.txt --full

  # CI environment with verification:
  $0 --venv .ci-venv --requirements requirements.txt --verify
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --venv)
            VENV_PATH="$2"
            shift 2
            ;;
        --requirements)
            REQUIREMENTS_FILE="$2"
            shift 2
            ;;
        --python)
            PYTHON_CMD="$2"
            shift 2
            ;;
        --full)
            FULL_INSTALL=true
            shift
            ;;
        --verify)
            VERIFY=true
            shift
            ;;
        --no-verify)
            VERIFY=false
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$VENV_PATH" ]]; then
    log_error "Missing required argument: --venv"
    show_help
    exit 1
fi

if [[ -z "$REQUIREMENTS_FILE" ]]; then
    log_error "Missing required argument: --requirements"
    show_help
    exit 1
fi

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    log_error "Requirements file not found: $REQUIREMENTS_FILE"
    exit 1
fi

# Check Python command availability
if ! command -v "$PYTHON_CMD" &> /dev/null; then
    log_error "Python command not found: $PYTHON_CMD"
    exit 1
fi

# Display Python version
PY_VERSION=$("$PYTHON_CMD" --version 2>&1)
log_info "Using Python: $PY_VERSION"

# Remove existing venv if present
if [[ -d "$VENV_PATH" ]]; then
    log_warn "Removing existing venv: $VENV_PATH"
    rm -rf "$VENV_PATH"
fi

# Create new venv
log_info "Creating virtual environment at: $VENV_PATH"
"$PYTHON_CMD" -m venv "$VENV_PATH"

# Activate venv (for verification only; actual activation happens in caller's shell)
VENV_PYTHON="$VENV_PATH/bin/python"
VENV_PIP="$VENV_PATH/bin/pip"

if [[ ! -f "$VENV_PYTHON" ]]; then
    log_error "Failed to create venv: $VENV_PYTHON not found"
    exit 1
fi

# Upgrade pip, setuptools, and wheel for deterministic installs
log_info "Upgrading pip, setuptools, and wheel..."
"$VENV_PIP" install --upgrade pip setuptools wheel

# Install requirements
log_info "Installing requirements from: $REQUIREMENTS_FILE"
"$VENV_PIP" install -r "$REQUIREMENTS_FILE"

# Verification step
if [[ "$VERIFY" == true ]]; then
    log_info "Running post-install verification..."
    
    # Check core runtime modules
    MODULES=("fastapi" "uvicorn" "pydantic" "requests")
    MISSING=()
    
    for module in "${MODULES[@]}"; do
        if ! "$VENV_PYTHON" -c "import $module" 2>/dev/null; then
            MISSING+=("$module")
        fi
    done
    
    if [[ ${#MISSING[@]} -gt 0 ]]; then
        log_error "Verification failed: missing modules: ${MISSING[*]}"
        exit 1
    fi
    
    log_info "Verification passed: all core runtime modules present"
    
    # Display installed packages summary
    log_info "Installed packages summary:"
    "$VENV_PIP" list --format=columns | head -15
fi

log_info "✓ Virtual environment built successfully: $VENV_PATH"
log_info "Activate with: source $VENV_PATH/bin/activate"
