#!/usr/bin/env bash
# Wrapper that loads JustNews environment variables before executing a command.
# It sources global config first, then overlays secrets when available.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Order matters: load global config first (non-secret defaults)
GLOBAL_SOURCES=(
    "/etc/justnews/global.env"
    "${REPO_ROOT}/global.env"
)

# Then overlay secrets from ephemeral/system/repo locations
SECRET_SOURCES=(
    "/run/justnews/secrets.env"        # preferred: ephemeral at runtime
    "/etc/justnews/secrets.env"        # system fallback
    "${REPO_ROOT}/secrets.env"         # local dev (gitignored)
)

loaded_global="false"
for env_file in "${GLOBAL_SOURCES[@]}"; do
    if [[ -f "${env_file}" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "${env_file}"
        set +a
        loaded_global="true"
        break
    fi
done

if [[ "${loaded_global}" != "true" ]]; then
    echo "WARNING: No global.env file found. Proceeding without loading non-secret project env vars." >&2
fi

# Load secrets on top if present (do not warn if absent)
for sec_file in "${SECRET_SOURCES[@]}"; do
    if [[ -f "${sec_file}" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "${sec_file}"
        set +a
        # do not break; allow later sources to override
    fi
done

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <command> [args...]" >&2
    exit 1
fi

# If caller wants to use `conda run ...` but `mamba` is available, prefer `mamba` as a drop-in replacement
# This makes CI and developer scripts faster when mamba is installed in the base env.
if [[ "$1" == "conda" ]]; then
    if command -v mamba >/dev/null 2>&1; then
        # Replace the leading 'conda' with 'mamba' and keep remaining args intact
        set -- "mamba" "${@:2}"
    fi
fi

exec "$@"
