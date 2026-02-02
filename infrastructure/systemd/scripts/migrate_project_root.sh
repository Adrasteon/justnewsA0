#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
# Usage: migrate_project_root.sh [--dry-run] [--create-symlink]

DRY_RUN=false
CREATE_SYMLINK=false
NEW_ROOT="${NEW_ROOT:-$HOME/JustNews}"
GLOBAL_ENV_FILE="/etc/justnews/global.env"

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --create-symlink) CREATE_SYMLINK=true; shift ;;
        -h|--help) echo "Usage: $SCRIPT_NAME [--dry-run] [--create-symlink]"; exit 0 ;;
        *) echo "Unknown option $1"; exit 1 ;;
    esac
done

echo "[INFO] Running project root migration checks"
echo "[INFO] New project root: $NEW_ROOT"

if [[ "$DRY_RUN" == "true" ]]; then
    echo "[INFO] Dry-run mode: no files will be changed"
fi

# 1) Update /etc/justnews/global.env (if present)
if [[ -f "$GLOBAL_ENV_FILE" ]]; then
    if grep -q "SERVICE_DIR=" "$GLOBAL_ENV_FILE"; then
        CURRENT=$(grep -E '^SERVICE_DIR=' "$GLOBAL_ENV_FILE" | cut -d'=' -f2-)
        echo "[INFO] Detected SERVICE_DIR=$CURRENT in $GLOBAL_ENV_FILE"
        if [[ "$CURRENT" != "$NEW_ROOT" ]]; then
            echo "[INFO] Replacing SERVICE_DIR in $GLOBAL_ENV_FILE"
            if [[ "$DRY_RUN" == "false" ]]; then
                sudo cp "$GLOBAL_ENV_FILE" "$GLOBAL_ENV_FILE.bak"
                sudo sed -i "s|^SERVICE_DIR=.*|SERVICE_DIR=$NEW_ROOT|" "$GLOBAL_ENV_FILE"
                echo "[SUCCESS] Updated SERVICE_DIR=$NEW_ROOT in $GLOBAL_ENV_FILE (backup: $GLOBAL_ENV_FILE.bak)"
            fi
        else
            echo "[INFO] SERVICE_DIR already correct"
        fi
    else
        echo "[WARN] SERVICE_DIR not present in $GLOBAL_ENV_FILE, adding it"
        if [[ "$DRY_RUN" == "false" ]]; then
            sudo cp "$GLOBAL_ENV_FILE" "$GLOBAL_ENV_FILE.bak"
            echo "SERVICE_DIR=$NEW_ROOT" | sudo tee -a "$GLOBAL_ENV_FILE" >/dev/null
            echo "[SUCCESS] Added SERVICE_DIR to $GLOBAL_ENV_FILE"
        fi
    fi
else
    echo "[WARN] $GLOBAL_ENV_FILE not found; if you plan to use env per-service, ensure SERVICE_DIR is set" 
fi

# 2) Optionally create an old-folder symlink if some on-disk references still use it
if [[ "$CREATE_SYMLINK" == "true" ]]; then
    # Legacy compatibility path - keep hardcoded as reference to old deployment
    ORIG_SYMLINK="/home/adra/JustNewsAgent-Clean"
    if [[ -e "$ORIG_SYMLINK" ]]; then
        echo "[INFO] $ORIG_SYMLINK already exists; skipping symlink creation"
    else
        echo "[INFO] Creating symlink $ORIG_SYMLINK -> $NEW_ROOT"
        if [[ "$DRY_RUN" == "false" ]]; then
            sudo ln -s "$NEW_ROOT" "$ORIG_SYMLINK"
            echo "[SUCCESS] Created symlink for compatibility"
        fi
    fi
fi

# 3) Reload systemd and restart justnews services
echo "[INFO] Reloading systemd units and restarting justnews services"
if [[ "$DRY_RUN" == "false" ]]; then
    sudo systemctl daemon-reload
    # Restart all units matching justnews@*.service
    for s in $(systemctl list-units --type=service --all | awk '{print $1}' | grep '^justnews@'); do
        sudo systemctl restart "$s" || sudo systemctl status "$s" --no-pager
    done
    echo "[SUCCESS] Systemd reloaded and justnews@ services restarted"
else
    echo "[DRY RUN] Skipping reload/restart"
fi

echo "[INFO] Migration check complete - run 'sudo systemctl status justnews@<agent>.service' for detailed status"

exit 0
