# Conda Environments & Packaging

This directory contains conda environment specifications for the 4 workflow phases, plus helper scripts and recipes for building conda packages.

---

## Phased Conda Environments (Quick Start)

JustNews uses **4 independent conda environments** to isolate CUDA/GPU dependencies across workflow phases.

### Quick Setup

```bash
cd /path/to/JustNews
bash scripts/dev/setup_dev_environment.sh --create-all-phases
bash scripts/dev/select_phase_env.sh --phase 1
source ./global.env

# Playwright browser binaries (required for crawler/browser automation in phase 1)
python -m playwright install --with-deps chromium
```

### Environment Files

| File | GPU | Purpose |
|------|-----|---------|
| `environment.base.yml` | ❌ | Shared base (common deps) |
| `environment.phase1.yml` | ✅ | Ingestion & Vectorization |
| `environment.phase2.yml` | ❌ | Clustering & Linkage (CPU-only) |
| `environment.phase3.yml` | ✅ | Synthesis & Curation |
| `environment.phase4.yml` | ❌ | Publishing & CMS (CPU-only) |

See [PHASED_ENVIRONMENT_MAPPING.md](PHASED_ENVIRONMENT_MAPPING.md) for full documentation.

---

## Conda Packaging Recipes

Conda packaging recipes and helper scripts for building conda packages that are required by this
project but are not available as compatible conda packages for our supported Python version(s).

### protobuf (python) recipe ------------------------

Location: conda/recipes/protobuf

Purpose: build a python `protobuf` package compatible with Python 3.12 in environments where conda-forge does not
provide a matching Python wheel.

How to use (locally)

1. Ensure `conda-build`or`mamba`(and`conda-build`) are installed in your
base environment.

1. From this repo root run:

```bash

# build into /tmp/conda-bld (or the conda-build configured output dir)

conda build conda/recipes/protobuf

```bash

1. If the build succeeds it will produce a conda package which can be installed
into your environment using `conda install --use-local protobuf`.

Contributing to conda-forge ---------------------------

If this recipe is useful, open a PR to the conda-forge `staged-recipes` repo following their contribution guidelines.
The recipe in this project is a starting point; maintainers may request updates (source urls, patches, pinning of
dependencies, etc.) before the final recipe is accepted into conda-forge.

Notes -----

- The recipe intentionally tries to use the upstream PyPI sdist as the source
and uses pip to build the wheel inside the conda-build environment so the compiled extension matches the local Python
ABI.

- Building protobuf can require a non-trivial build toolchain; CI or developer
machines must have the appropriate compilers and dependencies available.
