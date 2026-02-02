#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")

EXPECT_ROOT="$HOME/JustNews"
UNWANTED_ROOTS=("$HOME/JustNewsAgent-Clean" "$HOME/JustNewsAgent")

echo "[INFO] Checking systemd unit files use SERVICE_DIR env or working directory referencing project root"

check_unit() {
    local unit_file="$1"
    if [[ ! -f "$unit_file" ]]; then return; fi
    # Grep for $SERVICE_DIR or /opt/justnews or other allowed values
    if grep -q "\$SERVICE_DIR" "$unit_file" 2>/dev/null; then
        echo "[OK] $unit_file uses SERVICE_DIR"
        return
    fi
    if grep -q "/opt/justnews" "$unit_file" 2>/dev/null; then
        echo "[WARN] $unit_file uses /opt/justnews not $EXPECT_ROOT"
        return
    fi
    for bad in "${UNWANTED_ROOTS[@]}"; do
        if grep -q "$bad" "$unit_file" 2>/dev/null; then
            echo "[ERROR] $unit_file refers to deprecated path $bad"
        fi
    done
}

UNIT_DIRS=(/etc/systemd/system /lib/systemd/system $(pwd)/infrastructure/systemd/services)
for dir in "${UNIT_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        for f in "$dir"/*; do
            [[ -f "$f" ]] || continue
            check_unit "$f"
        done
    fi
done

echo "[INFO] Sanity check complete. If any [ERROR] lines were printed, update the unit files or env." 

exit 0
