## Running the full test-suite (including gated/integration tests)

Some tests are intentionally gated behind environment flags or require local external services (MariaDB, Redis, Chroma,
provider credentials). This document explains how to enable them for local runs and in CI.

High-level steps

1. Start the local infra required for integration/e2e tests

1. Export the environment flags that gate tests

1. Use the helper runner to load project env vars and run pytest

Note: Running `./scripts/dev/pytest.sh`with no arguments will now default to`pytest -vv`when run in an interactive
terminal (TTY) so you see per-test names and progress; in CI or non-interactive sessions it defaults to`pytest -q`. Pass
explicit pytest args to override this behavior.

Bring up services ----------------- The repository includes a helper compose file used by CI and local engineers.

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
