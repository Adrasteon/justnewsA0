#!/usr/bin/env bash
set -euo pipefail

# Usage: scripts/backup_conda_env.sh <env_name> <output_dir> [date]
# If `date` is provided (format YYYYMMDD), artifacts will be created
# with that suffix. If omitted the script will use UTC date (YYYYMMDD).
# Set DRY_RUN=1 to skip executing conda/python commands (useful for CI/tests).
# Default env: use canonical env when available
CANONICAL_ENV="${CANONICAL_ENV:-justnews-py312-phase1}"
ENV_NAME=${1:-${CANONICAL_ENV}}
OUTDIR=${2:-artifacts}
# optional 3rd argument is a date stamp (YYYYMMDD). If omitted we generate
# a UTC date string so backup files are date-stamped.
DATE=${3:-$(date -u +%Y%m%d)}

# A human-friendly base filename including date
BASE_NAME="${ENV_NAME}-${DATE}"

mkdir -p "$OUTDIR"

echo "Exporting conda environment: $ENV_NAME"

# create both a date-stamped snapshot and also update the non-dated canonical
# filenames so older processes can still expect ${ENV_NAME}.yml if desired.

if [[ -n "${DRY_RUN:-}" ]]; then
    echo "DRY RUN: would export YAML to $OUTDIR/${BASE_NAME}.yml and $OUTDIR/${ENV_NAME}.yml"
else
    conda env export -n "$ENV_NAME" --no-builds > "$OUTDIR/${BASE_NAME}.yml"
    # also keep an unversioned copy for convenience/back-compat
    conda env export -n "$ENV_NAME" --no-builds > "$OUTDIR/${ENV_NAME}.yml"
fi

if [[ -n "${DRY_RUN:-}" ]]; then
    echo "DRY RUN: would export explicit list to $OUTDIR/${BASE_NAME}.explicit.txt and $OUTDIR/${ENV_NAME}.explicit.txt"
else
    conda list --explicit -n "$ENV_NAME" > "$OUTDIR/${BASE_NAME}.explicit.txt"
    conda list --explicit -n "$ENV_NAME" > "$OUTDIR/${ENV_NAME}.explicit.txt"
fi

# Pack pip-installed packages (if any) from the environment
echo "Exporting pip packages for env: $ENV_NAME"

# Use conda run to avoid changing activated environment in caller
if [[ -n "${DRY_RUN:-}" ]]; then
    echo "DRY RUN: would export pip freeze to $OUTDIR/${BASE_NAME}.pip.txt and $OUTDIR/${ENV_NAME}.pip.txt"
else
    conda run -n "$ENV_NAME" python -m pip freeze --local > "$OUTDIR/${BASE_NAME}.pip.txt"
    conda run -n "$ENV_NAME" python -m pip freeze --local > "$OUTDIR/${ENV_NAME}.pip.txt"
fi

# Pack entire env if conda-pack is available
if command -v conda-pack >/dev/null 2>&1; then
    echo "Creating condapack tarball for: $ENV_NAME"
    if [[ -n "${DRY_RUN:-}" ]]; then
        echo "DRY RUN: would create $OUTDIR/${BASE_NAME}.tar.gz and $OUTDIR/${ENV_NAME}.tar.gz using conda-pack"
    else
        conda pack -n "$ENV_NAME" -o "$OUTDIR/${BASE_NAME}.tar.gz"
        # keep a latest-friendly tarball as well
        conda pack -n "$ENV_NAME" -o "$OUTDIR/${ENV_NAME}.tar.gz"
    fi
else
    echo "Warning: conda-pack not installed. Skipping packed tarball. Use 'conda install -c conda-forge conda-pack' to enable this"
fi

# Output artifacts
ls -l "$OUTDIR"/*${ENV_NAME}* || true

echo "Backup complete: artifacts in $OUTDIR (dated: $DATE)"
