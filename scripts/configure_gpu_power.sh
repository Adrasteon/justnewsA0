#!/usr/bin/env bash
# Configure GPU Power Limit to 300W for stability/efficiency
# Requires sudo privileges
set -euo pipefail

TARGET_POWER=300

# Get the first value found. Output typically looks like "Current Power Limit : 350.00 W"
# We take column 5. We use head -n 1 to ensure we only grab the first GPU's limit if multiple exist or if N/A fields appear.
current_limit=$(nvidia-smi -q -d POWER | grep "Current Power Limit" | awk '{print $5}' | head -n 1)
echo "Current Power Limit: ${current_limit}W"

if [[ "$current_limit" == "N/A" ]]; then
    echo "Could not determine current power limit (N/A). Skipping."
    exit 0
fi

if [[ "$(echo "$current_limit > $TARGET_POWER" | bc -l)" -eq 1 ]]; then
    echo "Limit is higher than ${TARGET_POWER}W. Attempting to clamp to ${TARGET_POWER}W..."
    if [ "$EUID" -ne 0 ]; then 
        echo "Error: This script must be run as root to change power settings."
        echo "Try: sudo $0"
        exit 1
    fi
    nvidia-smi -pl $TARGET_POWER
    echo "Power limit set to ${TARGET_POWER}W."
else
    echo "Power limit is already at or below ${TARGET_POWER}W. No action needed."
fi
