# Testing the GPU Orchestrator (developer & CI guide)

This doc covers the recommended testing strategies for the GPU orchestrator: quick local unit/integration tests using
in-memory emulators, deeper systemd- based containers for system-level testing, and CI configuration that runs tests in
the canonical UV/venv environment used by developers.

Why this matters

- The orchestrator interacts with production services (MariaDB and Redis streams) — tests should be fast and hermetic
  during development but there are cases where you want higher fidelity tests that exercise systemd and service
  behavior.

Test tiers

1. Fast unit & integration tests (local dev) — use in-memory sqlite + in-memory Redis emulator

- Location: `tests/unit/`and`tests/integration/`

- Fast, deterministic, no external infra required

- Use the pytest helper script to ensure you run tests inside the project's UV/venv environment:

./scripts/dev/pytest.sh [pytest args]

- The tests include helpers that map MySQL `%s`placeholders to sqlite`?` for compatibility in CI and developer runs.

1. Systemd-level local tests — optional, opt-in, higher fidelity

- Use the repository-provided systemd-nspawn helper `scripts/dev/run_systemd_nspawn_env.sh`to create an Ubuntu-based
  systemd container and install`mariadb-server`and`redis-server` inside it.

- This is useful for reproducing systemd/service unit ordering issues, DB startup ordering, or other system-level
  behavior that in-memory emulators won't show.

- Steps (example):

sudo scripts/dev/run_systemd_nspawn_env.sh create sudo scripts/dev/run_systemd_nspawn_env.sh start sudo
scripts/dev/run_systemd_nspawn_env.sh install sudo scripts/dev/run_systemd_nspawn_env.sh shell  # to inspect and run
tests in the container

- The helper is intentionally opt-in and requires root or privilege. For teams that want easier management and
  clustering of system containers, consider LXD on developer machines or on self-hosted runners.

1. CI-level fidelity tests

  - The repository CI workflow has been updated to use Miniconda and create a `${CANONICAL_ENV:-justnews-py312}`conda
    environment in CI, matching local dev setups; CI now runs`pytest` inside that environment.

- If you want true end-to-end tests hitting live Redis and MariaDB, prefer a dedicated CI job that runs on self-hosted
  runners capable of running systemd-nspawn or LXD (not possible on the default hosted runners due to privilege
  constraints). Adding such a CI job is recommended for deeper validation but needs self-hosted capabilities.

  - Docker-based E2E PoC (test/CI only): We added a lightweight Docker Compose-based PoC which boots a pre-seeded
    MariaDB and Redis for faster E2E verification without requiring systemd-nspawn privileges. This PoC is intended for
    testing/CI only — the canonical MariaDB deployment in developer and production workflows runs on the host (outside
    Docker) or as a managed service. See `scripts/dev/docker-
    compose.e2e.yml`,`scripts/dev/run_e2e_docker.sh`and`.github/workflows/e2e-docker.yml`.

Developer ergonomics & helpers -- `scripts/dev/pytest.sh`— wrapper which runs pytest inside`${CANONICAL_ENV:-justnews-
py312}`conda env and sets`PYTHONPATH` to the repo root. Use it for consistent local runs.

- `scripts/dev/install_hooks.sh`— installs local git hooks (from`scripts/dev/git-hooks/`) into`.git/hooks`(opt-in).
  The`pre-push`hook prints guidance and can optionally run a quick smoke test when`GIT_STRICT_TEST_HOOK=1`.

- `tests/conftest.py` includes a safety check that enforces local pytest runs in supported envs
  (project `.venv` / `/deps/.venv` / canonical phase envs) by default.
  CI bypasses this check.
  Developers may bypass locally with `ALLOW_ANY_PYTEST_ENV=1` only for temporary debugging,
  and must not use that bypass in canonical CI or release validation paths.

Practical commands

- Run all unit tests quickly:

./scripts/dev/pytest.sh -q -k "not integration"

- Run integration tests (fast in-memory harness):

./scripts/dev/pytest.sh -q tests/integration -q

- Run worker flow integration test specifically (smoke):

./scripts/dev/pytest.sh -q tests/integration/test_worker_flow.py::test_worker_cl aims_lease_runs_and_updates_db -q -s

Running full, real E2E tests inside a systemd-nspawn container (self-hosted runner)
--------------------------------------------------------------------------

Once you have a self-hosted runner prepared (see `scripts/dev/setup_selfhosted_runner.sh`) and a running systemd-nspawn
container bootstrapped (the CI workflow covers this), you can run the full E2E suite inside the container with:

```bash

## from the runner or inside the container shell

cd /root/justnews
E2E_REAL=1 PYTEST_RUNNING=1 PYTHONPATH=/root/justnews python3.11 -m pytest tests/e2e -q -s

```

The E2E tests are gated by the `E2E_REAL=1` environment variable so they won't run in standard CI or local developer
runs unless explicitly enabled.

Tips & gotchas

- In-memory tests are intentionally opinionated to keep CI fast and deterministic — they simulate Redis/XGROUP semantics
  and map SQL placeholder differences. Use systemd-nspawn or CI self-hosted jobs only when you need production fidelity.

- When debugging a failing integration test, try:

- Enabling more verbose pytest output (-vv or -s) and reviewing debug prints in `agents/gpu_orchestrator/worker.py` and
  engine logs

- Spawning a systemd-nspawn container and running the engine against a real MariaDB inside the container to identify
  behaviour differences between sqlite and MariaDB

- Running the Docker-based PoC locally (for testing/CI debugging only):
1) Start services: `docker-compose -f scripts/dev/docker-compose.e2e.yml up -d --build` 2) Run the smoke tests:
`scripts/dev/e2e_smoke.sh`3) Run full E2E: set the env vars described in`scripts/dev/run_e2e_docker.sh` and run
`pytest -q tests/e2e -q -s`

Where to add tests

- Add new unit tests in `tests/unit/`for engine methods (lease persistence, leader election mocks, reclaimer), and
  integration tests in`tests/integration/` for end-to-end flows (submit->claim->done, DLQ handling, reclaimer pass).
  Follow patterns seen in the repository for sqlite/redis emulators to remain CI-friendly.
