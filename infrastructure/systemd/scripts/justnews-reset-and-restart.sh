#!/bin/bash

# JustNews Reset and Restart Script
# This script shuts down, resets, and restarts the entire JustNews system.

set -e  # Exit immediately if a command exits with a non-zero status

# Dynamically determine the project root based on the script's location
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR/../../..")"
ENV_FILE="/etc/justnews/global.env"

# Activate Conda environment
if [[ -n "$SUDO_USER" ]]; then
    CONDA_BASE="$(sudo -Hiu "$SUDO_USER" bash -lc 'echo "$HOME"')/miniconda3"
else
    CONDA_BASE="$HOME/miniconda3"
fi
if [[ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh"
    conda activate ${CANONICAL_ENV:-justnews-py312-phase1}
else
    echo "Conda initialization script not found at $CONDA_BASE/etc/profile.d/conda.sh"
    exit 1
fi

# Print environment variables for debugging
echo "Environment variables for debugging:" >&2
env >&2

# Load environment variables
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment variables from $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "Environment file $ENV_FILE not found. Exiting."
    exit 1
fi

# Step 1: Preflight Checks
echo "Running preflight checks..."
$PROJECT_ROOT/infrastructure/systemd/scripts/justnews-preflight-check.sh --gate-only

# Step 2: Shutdown Services
echo "Stopping all JustNews services..."
systemctl stop 'justnews@*'

# Step 3: Reset Database (Optional)
# Uncomment the following lines if database reset is required
# echo "Resetting database..."
# psql -U $POSTGRES_USER -d $POSTGRES_DB -c "TRUNCATE TABLE some_table RESTART IDENTITY;"

# Step 4: Clear Temporary Files
echo "Clearing temporary files..."
rm -rf /tmp/justnews/*

# Step 5: Restart Services
echo "Starting all JustNews services..."
$PROJECT_ROOT/infrastructure/systemd/scripts/enable_all.sh start

# Step 6: Verify Status
echo "Verifying system status..."
$PROJECT_ROOT/infrastructure/systemd/scripts/justnews-system-status.sh

# Debug NVML Initialization
echo "Testing NVML Initialization..."
python3 -c "from pynvml import nvmlInit, nvmlShutdown; nvmlInit(); print('NVML Initialized'); nvmlShutdown()" || echo "NVML Initialization failed in script context."

echo "JustNews system reset and restart completed successfully."