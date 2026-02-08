#!/usr/bin/env bash
# setup_preflight_nopasswd.sh
# Safely configure a sudoers NOPASSWD rule to run preflight.sh without prompts,
# validate with visudo, and optionally run the preflight to verify behavior.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_PREFLIGHT="${SCRIPT_DIR}/preflight.sh"
SUDOERS_DROPIN="/etc/sudoers.d/justnews-preflight"
TMP_DROPIN="/tmp/justnews-preflight.$$"

TARGET_USER="${SUDO_USER:-${USER}}"
PREFLIGHT_PATH="${PREFLIGHT_PATH:-$DEFAULT_PREFLIGHT}"
BASH_PATH="${BASH_PATH:-$(command -v bash || echo /bin/bash)}"

# Logs under XDG cache (non-root location)
CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/justnews/preflight"
LOG_PATH="$CACHE_DIR/preflight_sudo_debug.out"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--user USER] [--preflight /abs/path/to/preflight.sh] [--install-only] [--run-gate-only [INSTANCE]] [--run-full] [--timeout SECONDS] [--uninstall] [--dry-run]

Options:
  --user USER           Username to grant NOPASSWD to (default: current user)
  --preflight PATH      Absolute path to preflight.sh (default: autodetected)
  --install-only        Install sudoers drop-in but do not run preflight (default)
  --run-gate-only [INST] Run preflight in gate-only mode; optional instance (e.g., mcp_bus)
  --run-full            Run full preflight checks (may fail in a running system)
  --timeout SECONDS     Override gate-only timeout (env GATE_TIMEOUT)
  --uninstall           Remove the sudoers drop-in and exit
  --dry-run             Show intended changes without modifying the system

Environment overrides:
  TARGET_USER, PREFLIGHT_PATH, BASH_PATH
EOF
}

INSTALL_ONLY=1
RUN_GATE_ONLY=0
RUN_FULL=0
TIMEOUT=""
UNINSTALL=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      TARGET_USER="$2"; shift 2 ;;
    --preflight)
      PREFLIGHT_PATH="$2"; shift 2 ;;
    --install-only)
      INSTALL_ONLY=1; RUN_GATE_ONLY=0; RUN_FULL=0; shift ;;
    --run-gate-only)
      RUN_GATE_ONLY=1; INSTALL_ONLY=0; RUN_FULL=0;
      # Optional instance argument
      if [[ ${2:-} != "" && ${2:-} != -* ]]; then
        GATE_INSTANCE="$2"; shift 2;
      else
        shift;
      fi
      ;;
    --run-full)
      RUN_FULL=1; INSTALL_ONLY=0; RUN_GATE_ONLY=0; shift ;;
    --timeout)
      TIMEOUT="$2"; shift 2 ;;
    --uninstall)
      UNINSTALL=1; shift ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }; }

require_cmd sudo
require_cmd visudo

if [[ "$UNINSTALL" -eq 1 ]]; then
  echo "Removing sudoers drop-in: ${SUDOERS_DROPIN}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] Would remove: $SUDOERS_DROPIN"
    exit 0
  fi
  sudo rm -f "$SUDOERS_DROPIN"
  sudo visudo -c
  echo "Removed."
  exit 0
fi

if [[ ! -f "$PREFLIGHT_PATH" ]]; then
  echo "preflight.sh not found at: $PREFLIGHT_PATH" >&2
  exit 1
fi

# Ensure preflight is executable (non-fatal if cannot)
chmod +x "$PREFLIGHT_PATH" 2>/dev/null || true

# Resolve absolute paths
PREFLIGHT_PATH="$(readlink -f "$PREFLIGHT_PATH")"
BASH_PATH="$(readlink -f "$BASH_PATH" || echo "$BASH_PATH")"

echo "Configuring NOPASSWD for user=${TARGET_USER}"
echo " - preflight: ${PREFLIGHT_PATH}"
echo " - bash:      ${BASH_PATH}"

# Build sudoers content (include exact invocations we might use)
cat > "$TMP_DROPIN" <<EOF
# Allow ${TARGET_USER} to run preflight without password
${TARGET_USER} ALL=(ALL) NOPASSWD: \
  ${PREFLIGHT_PATH}, \
  ${BASH_PATH} ${PREFLIGHT_PATH}, \
  ${BASH_PATH} -x ${PREFLIGHT_PATH}
EOF

echo "Validating sudoers drop-in syntax..."
sudo visudo -cf "$TMP_DROPIN"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[DRY-RUN] Would install sudoers drop-in to ${SUDOERS_DROPIN} with content:"
  cat "$TMP_DROPIN"
  rm -f "$TMP_DROPIN"
  exit 0
fi

echo "Installing sudoers drop-in to ${SUDOERS_DROPIN}"
# Backup existing file if present
if sudo test -f "$SUDOERS_DROPIN"; then
  TS=$(date +%Y%m%d_%H%M%S)
  sudo cp -p "$SUDOERS_DROPIN" "${SUDOERS_DROPIN}.bak_${TS}"
  echo "Backup created: ${SUDOERS_DROPIN}.bak_${TS}"
fi

# Install atomically with proper owner/perms
set +e
sudo install -o root -g root -m 0440 "$TMP_DROPIN" "$SUDOERS_DROPIN"
INSTALL_RC=$?
set -e
rm -f "$TMP_DROPIN"

if [[ $INSTALL_RC -ne 0 ]]; then
  echo "Failed to install sudoers drop-in (rc=$INSTALL_RC)" >&2
  exit $INSTALL_RC
fi

echo "Re-validating full sudoers configuration..."
if ! sudo visudo -c; then
  echo "visudo validation failed; attempting rollback..." >&2
  if sudo test -f "${SUDOERS_DROPIN}.bak_${TS:-}"; then
    sudo mv -f "${SUDOERS_DROPIN}.bak_${TS}" "$SUDOERS_DROPIN"
    sudo visudo -c || true
  fi
  exit 1
fi

if [[ "$INSTALL_ONLY" -eq 1 && "$RUN_GATE_ONLY" -eq 0 && "$RUN_FULL" -eq 0 ]]; then
  echo "Install-only mode complete."
  exit 0
fi

# Prepare logging location
mkdir -p "$CACHE_DIR" || true
echo "Running preflight with sudo (non-interactive)..."
set +e
# Build command based on mode; prefer running the script path directly so sudoers matches exactly
CMD=(sudo -n "$PREFLIGHT_PATH")
if [[ "$RUN_GATE_ONLY" -eq 1 ]]; then
  if [[ -n "$TIMEOUT" ]]; then
    CMD=(sudo -n env GATE_TIMEOUT="$TIMEOUT" "$PREFLIGHT_PATH" --gate-only ${GATE_INSTANCE:-})
  else
    CMD=(sudo -n "$PREFLIGHT_PATH" --gate-only ${GATE_INSTANCE:-})
  fi
elif [[ "$RUN_FULL" -eq 1 ]]; then
  CMD=(sudo -n "$PREFLIGHT_PATH")
fi

# shellcheck disable=SC2068
"${CMD[@]}" | tee "$LOG_PATH"
STATUS=${PIPESTATUS[0]}
set -e

echo
echo "Preflight exit code: $STATUS"
echo "Log saved to: $LOG_PATH"
echo "Cache dir: $CACHE_DIR"
exit "$STATUS"
