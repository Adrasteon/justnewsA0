## Dev Setup — Reproducible Environment for Live-Run Testing

This file outlines the minimal reproducible steps required to run a local dev stack for JustNews live-run testing and phase-specific development.

### Understanding the Phased Environment System

JustNews uses **4 isolated conda environments**, one for each workflow phase:

| Phase | Environment | Purpose | GPU? |
|-------|-------------|---------|------|
| 1 | `justnews-py312-phase1` | Ingestion, embeddings, crawler | ✅ Yes |
| 2 | `justnews-py312-phase2` | Clustering, analytics, unit tests | ❌ CPU |
| 3 | `justnews-py312-phase3` | Synthesis, LLM inference | ✅ Yes |
| 4 | `justnews-py312-phase4` | Publishing, Django, web | ❌ CPU |

Tests are run **per-phase** in their respective environments to avoid dependency conflicts.

### Prerequisites

- Docker / docker-compose or equivalent
- git
- conda or mamba (recommended: Python 3.12)

### Create the Phased Python Environments

The phased conda environments are built from versioned YAML specifications in `conda/environment.phase{1,2,3,4}.yml`.

**Option 1: Automated build (Recommended)**
```bash
# Build all 4 phased environments in sequence
bash scripts/build_phased_envs.sh
```

**Option 2: Manual build per phase**
```bash
# Build or update individual phase environments
conda env create -f conda/environment.phase1.yml -n justnews-py312-phase1
conda env create -f conda/environment.phase2.yml -n justnews-py312-phase2
conda env create -f conda/environment.phase3.yml -n justnews-py312-phase3
conda env create -f conda/environment.phase4.yml -n justnews-py312-phase4
```

**Activate Phase 1 (GPU ingestion) for development:**
```bash
conda activate justnews-py312-phase1
playwright install   # Install browser dependencies
```

### Development Workflow by Phase

- **Phase 1 Development**: `conda activate justnews-py312-phase1` + GPU available
- **Phase 2 Development**: `conda activate justnews-py312-phase2` + no GPU needed
- **Phase 3 Development**: `conda activate justnews-py312-phase3` + GPU for LLM inference
- **Phase 4 Development**: `conda activate justnews-py312-phase4` + no GPU needed

Build local MariaDB image (used for tests / local dev)

```bash
docker build -f scripts/dev/db-mariadb/Dockerfile -t justnews-mariadb:latest scripts/dev

```

Start a minimal local stack (db + redis) for smoke/e2e tests

```bash
docker-compose -f scripts/dev/docker-compose.e2e.yml up -d db redis

```bash

Verify local services

```bash

## DB check (mysql client may be required)

mysql -h 127.0.0.1 -P 13306 -u justnews -ptest -e "SELECT 1;"

## Redis check

redis-cli -h 127.0.0.1 -p 16379 PING

## Chroma can be started separately if needed using the official image

docker run --rm -p 8000:8000 chromadb/chroma:0.4.18

```

Running tests — smoke/unit

For phase-specific testing, use the phased test runner:

```bash
# Run Phase 1 tests (GPU ingestion)
./scripts/run_phase_tests.sh 1

# Run Phase 2 tests (CPU clustering)
./scripts/run_phase_tests.sh 2

# Run all phases sequentially
./scripts/run_phase_tests.sh all

# Run with verbose output
./scripts/run_phase_tests.sh 1 --verbose

# Discover tests without running them
./scripts/run_phase_tests.sh 1 --collect-only
```

**Via Makefile (easier):**
```bash
make test-phase1         # Phase 1 only
make test-phased         # All phases
make test-phase-discovery  # Discover all tests
```

**Direct pytest (advanced):**
```bash
# Run Phase 2 tests in Phase 2 environment
conda run -n justnews-py312-phase2 pytest tests/ -m "phase2" -v

# Run non-integration tests only
conda run -n justnews-py312-phase1 pytest tests/ -m "not integration" -v
```

### Troubleshooting Test Failures

If tests fail during build:

1. Check environment activation: `conda info --envs`
2. Verify dependencies: `conda list -n justnews-py312-phase1`
3. Review test output for specific import errors
4. Check [TESTING.md](TESTING.md) for gated test requirements

If you run into environment issues, check `conda/environment.phase*.yml` and ensure all required channels are available.
