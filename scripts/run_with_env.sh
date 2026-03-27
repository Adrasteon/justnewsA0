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

# Legacy compatibility: map `conda run -n <env> ...` to canonical UV/.venv python
# for scripts that have not been fully migrated yet.
if [[ "$1" == "conda" && "${2:-}" == "run" ]]; then
    shift 2
    if [[ "${1:-}" == "-n" || "${1:-}" == "--name" ]]; then
        shift 2
    fi
    if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
        set -- "${REPO_ROOT}/.venv/bin/python" "$@"
    else
        set -- "python" "$@"
    fi
fi

exec "$@"
