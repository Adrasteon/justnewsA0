# Conda Environment Backup & Restore

This document explains how to back up and restore the `${CANONICAL_ENV:-justnews-py312-phase1}` conda environment used by the
project.

## Why back up the environment

- To ensure reproducible test and CI runs

- To share an exact runtime with collaborators

- To provide a fallback when troubleshooting or reverting

## Artifacts and what they contain

- environment.yml: conda YAML export (usually no-builds) — re-create environment with conda.

- explicit spec: conda explicit spec — exact binary package list (OS-specific).

- pip-freeze.txt: pip packages installed inside environment (optional restore via pip).

- conda-pack tarball: full environment runtime packaged as a `.tar.gz`.

## Commands

- Create artifacts using the helper script (recommended):

```bash

## Back up the conda environment to artifacts/ (will also create a date-stamped copy)

## Example: writes these files in artifacts/:

## - ${CANONICAL_ENV:-justnews-py312}.yml

## - ${CANONICAL_ENV:-justnews-py312}-YYYYMMDD.yml

## - ${CANONICAL_ENV:-justnews-py312}.explicit.txt

## - ${CANONICAL_ENV:-justnews-py312}-YYYYMMDD.explicit.txt

## - ${CANONICAL_ENV:-justnews-py312}.pip.txt

## - ${CANONICAL_ENV:-justnews-py312}-YYYYMMDD.pip.txt

./scripts/backup_conda_env.sh ${CANONICAL_ENV:-justnews-py312} artifacts

## Optionally provide an explicit date (UTC) to the script instead of using today's

## date -- useful when scripting: e.g. $(date -u +%Y%m%d)

./scripts/backup_conda_env.sh ${CANONICAL_ENV:-justnews-py312} artifacts $(date -u +%Y%m%d)

## For CI/tests where conda may not be available, use a dry-run to validate outputs

## without running conda: the script will print the files it would create.

DRY_RUN=1 ./scripts/backup_conda_env.sh ${CANONICAL_ENV:-justnews-py312} artifacts 20251123

```bash

- To restore from YAML:

```bash
conda env create -f artifacts/${CANONICAL_ENV:-justnews-py312}.yml -n ${CANONICAL_ENV:-justnews-py312}-restored

## Optionally: pip install -r artifacts/${CANONICAL_ENV:-justnews-py312}.pip.txt

```

- To restore from explicit spec (exact binary builds):

```bash
conda create --name ${CANONICAL_ENV:-justnews-py312}-restored --file artifacts/${CANONICAL_ENV:-justnews-py312}.explicit.txt

```bash

- To unpack the condapack tarball:

```bash
mkdir -p ~/envs/${CANONICAL_ENV:-justnews-py312}-unpacked
tar -xzf artifacts/${CANONICAL_ENV:-justnews-py312}.tar.gz -C ~/envs/${CANONICAL_ENV:-justnews-py312}-unpacked
~/envs/${CANONICAL_ENV:-justnews-py312}-unpacked/bin/conda-unpack

```

- Re-run preflight checks and tests after restoring:

```bash
conda run -n ${CANONICAL_ENV:-justnews-py312}-restored python scripts/check_protobuf_version.py
conda run -n ${CANONICAL_ENV:-justnews-py312}-restored python scripts/check_deprecation_warnings.py

```

## Notes

- The `explicit` spec pins precise builds. It is OS-specific — use on the same platform as the original environment.

- If you are using conda-forge packages (recommended), prefer reinstalling or using conda-lock for cross-platform
  reproducibility.

- After restore, re-run `scripts/check_deprecation_warnings.py`. If it detects deprecation warnings (particularly
  from`google._upb`), re-install`protobuf`and recompilation-dependent wheels (either with`pip --no-binary` or via the
  conda package).

- When migrating from the legacy `justnews-py312` environment, export `CANONICAL_ENV=justnews-py312-phase1` temporarily so
  automation keeps working until you finish creating the new `${CANONICAL_ENV:-justnews-py312-phase1}` phased environment.

## Troubleshooting

- Deprecation warnings caused by compiled extensions imply a mismatch between the runtime’s `upb` and compiled wheels;
  best approach is to reinstall compatible wheels rather than attempting to mask the warning.

- For CI reproducibility: prefer building or pinning environment from `explicit`specs or`conda-lock` artifacts.
