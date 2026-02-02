## Running Tests – Phased Environment System

JustNews uses a **phased testing strategy** where each workflow phase runs in its own isolated conda environment. This means:
- **Phase 1** (GPU Ingestion): `justnews-py312-phase1` – GPU-enabled, crawler, embeddings tests
- **Phase 2** (CPU Clustering): `justnews-py312-phase2` – CPU clustering, analytics, unit tests
- **Phase 3** (GPU Synthesis): `justnews-py312-phase3` – GPU synthesis, LLM inference tests
- **Phase 4** (CPU Publishing): `justnews-py312-phase4` – Django, publishing, web tests

### Quick Start: Running Phased Tests

**Run all phases sequentially:**
```bash
make test-phased
```

**Run a specific phase:**
```bash
make test-phase1    # or test-phase2, test-phase3, test-phase4
```

**Run via the test runner script directly:**
```bash
./scripts/run_phase_tests.sh 1              # Phase 1
./scripts/run_phase_tests.sh all            # All phases
./scripts/run_phase_tests.sh 1 --verbose    # Verbose output
./scripts/run_phase_tests.sh 1 --strict     # Stop on first failure
./scripts/run_phase_tests.sh all --collect-only  # Discover tests without running
```

### Advantages of Phased Testing

1. **Environment Isolation**: No dependency conflicts between phases
2. **Clear Ownership**: Failures are tied to specific phases
3. **Parallelizable**: Phases can run in parallel in CI/CD
4. **Deterministic**: Fixed dependencies per phase ensure reproducible results
5. **GPU Efficiency**: GPU tests (phases 1 & 3) don't conflict with CPU tests (phases 2 & 4)

### Test Markers

Tests are tagged with phase markers: `@pytest.mark.phase1`, `@pytest.mark.phase2`, etc.

**Run tests for a specific phase with markers:**
```bash
conda run -n justnews-py312-phase1 pytest -m phase1
```

**Run tests excluding a phase:**
```bash
conda run -n justnews-py312-phase1 pytest -m "not phase2 and not phase3 and not phase4"
```

### Understanding Test Output

```bash
$ make test-phase1
===========================================
Phase 1: GPU Ingestion, Embedding, Crawler (Phase 1)
Environment: justnews-py312-phase1
===========================================
collected 66 items / 1 error / 34 deselected / 1 skipped

# 66 tests collected for Phase 1
# 1 error in collection (non-critical dependency issue)
# 34 tests deselected (marked for other phases)
# 1 test skipped (environment condition not met)
```

---

## Running the Full Test Suite (Including Gated/Integration Tests)

```bash

# Start services in the background

docker compose -f scripts/dev/docker-compose.e2e.yml up -d

## (optional) view service health

docker compose -f scripts/dev/docker-compose.e2e.yml ps

```yaml

Enable gated tests ------------------ Set the gates for the classes of tests you want to run. Example — run *all* gated
tests:

```bash
export RUN_REAL_E2E=1                # e2e tests backed by local Redis + MariaDB
export ENABLE_DB_INTEGRATION_TESTS=1 # integration tests that need MariaDB
export ENABLE_CHROMADB_LIVE_TESTS=1  # live ChromaDB + embedding model tests
export RUN_PROVIDER_TESTS=1          # provider-run tests (HF/OpenAI)

## For provider tests (OpenAI) you must also export credentials

export OPENAI_API_KEY="<your-openai-key>"

## Your project env (global.env) is loaded by scripts/run_with_env.sh; it includes CHROMADB_* and MARIADB_* defaults

## Run tests via the helper

./scripts/dev/run_e2e_with_env.sh -q

```

Notes -----

- For Chroma, `scripts/dev/docker-compose.e2e.yml`configures Chroma to listen on port 3307 and exposes host port 3307
  (the project default found in`global.env`). If you change CHROMADB_PORT in`global.env`, update the compose file
  accordingly.

- If you only want to run a subset, just export the matching flags. For example `export ENABLE_CHROMADB_LIVE_TESTS=1`
  and run only the chroma integration tests.

- CI mirrors this pattern in `.github/workflows/editorial-harness.yml` — review that workflow to reproduce CI
  environment locally.

Troubleshooting ---------------

- If tests still skip, check `pytest -q -r s` for skip reasons.

- Ensure Docker is running, and the images are healthy (use `docker compose ps`and`docker compose logs <service>`).

- For provider tests, ensure you have valid API keys and any required model selection env vars (HF_TEST_MODEL,
  OPENAI_MODEL).

If you'd like, I can add a CI job that runs the full gated test matrix nightly so we catch integration regressions early
— say the word and I'll prepare the workflow change.
