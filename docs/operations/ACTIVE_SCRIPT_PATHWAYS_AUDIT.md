---
title: Active Script Pathway Audit
description: Comprehensive map of active script workflows, branches, and operational pathways in JustNews
---

# Active Script Pathway Audit

This document maps active script-driven pathways in JustNews after conda deprecation and root-script retirement cleanup.

## Audit scope and method

- Scope: tracked `.sh`/`.py` scripts under `scripts/`, `infrastructure/systemd/`, and root-level script entrypoints.
- Inventory source: `docs/operations/_script_audit_inventory.json` (generated from repository scan).
- Counts: total scripts=843, active(non-retired)=782, retired stubs=61, scripts with inbound callers=47.
- Reference graph sources: Makefile, GitHub workflows, systemd scripts/units/docs, scripts tree.
- Exclusions: `archive_local/` and archive-only materials are non-active by policy.

## Global lifecycle model

1) Environment bootstrap (UV/.venv)
2) Service startup and orchestration (Docker-first canonical runtime)
3) Data pipeline execution (crawl → ingest → memory/archive → orchestrator)
4) Observability and governance controls
5) CI/test/lint quality gates
6) Optional indexing and developer tooling
7) Controlled fallback pathways for compatibility stubs

## Canonical entrypoint scripts (active)

| Script | Role | Inbound callers |
|---|---|---|
| `start_all_services.sh` | Docker-canonical lifecycle wrapper (`docker_compose.sh up`) | operator/manual |
| `stop_all_services.sh` | Docker-canonical lifecycle wrapper (`docker_compose.sh down`) | operator/manual |
| `scripts/ops/docker_compose.sh` | Docker compose lifecycle wrapper (`up/down/status/logs/ps`) | Makefile, wrappers |
| `scripts/ops/docker_preflight.sh` | Docker runtime preflight validation | Makefile |
| `scripts/ops/run_crawl_schedule.py` | scheduler trigger for crawler jobs | infrastructure/systemd/scripts/run_crawl_schedule.sh |
| `scripts/run_with_env.sh` | global env/secrets command wrapper | scripts/dev/run_e2e_with_env.sh |
| `scripts/run_tests_with_env.sh` | preset-based test launcher | - |
| `scripts/dev/pytest.sh` | UV-aware pytest wrapper | Makefile, scripts/dev/run_full_pytest_safe.sh, scripts/dev/run_pytest_conda.sh |
| `scripts/dev/run_full_pytest_safe.sh` | safe-mode full test wrapper | Makefile |
| `scripts/dev/check_canonical_env.sh` | legacy conda literal policy gate | .github/workflows/pytest.yml |
| `scripts/ops/enable_governor.sh` | memory governor activation | - |
| `scripts/ops/disable_governor.sh` | memory governor deactivation | - |
| `scripts/indexing/build_code_index.py` | code index builder | Makefile, scripts/indexing/autonomous_index_update.py, scripts/indexing/daily_hermes_refresh.sh, scripts/indexing/query_code_index.py, scripts/indexing/session_chat_init.sh |
| `scripts/indexing/query_code_index.py` | code index query tool | Makefile |
| `scripts/indexing/index_autoupdate_daemon.sh` | index auto-update daemon | Makefile, scripts/indexing/session_chat_init.sh |

## Docker-canonical operational pathway (primary path)

Primary control scripts:
- `scripts/ops/docker_preflight.sh`
- `scripts/ops/docker_compose.sh`
- `start_all_services.sh` / `stop_all_services.sh` (thin wrappers)
- compose file: `infrastructure/docker/docker-compose.canonical.yml`

Flow:
1. Operator runs preflight (`make docker-preflight` or script directly).
2. Operator starts stack via `make deploy-docker` or `./start_all_services.sh`.
3. Compose brings up canonical services/agents.
4. Operator checks status/logs via Makefile or compose wrapper.
5. Operator stops stack via `make deploy-docker-stop` or `./stop_all_services.sh`.

Branch pathways in Docker flow:
- Branch A: `JUSTNEWS_COMPOSE_FILE` override selects alternate compose file.
- Branch B: direct compose wrapper usage (`up/down/status/logs/ps`) for targeted operations.
- Branch C: optional systemd fallback only for explicit non-canonical/legacy operations.

## Non-systemd daemon pathway (secondary/legacy active path)

Legacy daemon scripts (`scripts/ops/start_services_daemon.sh`, `scripts/ops/stop_services.sh`) remain available only as non-canonical fallback paths.
Flow highlights:
- direct host process orchestration without Docker compose canonical lifecycle.
- retained for constrained transition scenarios and historical troubleshooting only.
Branch pathways:
- port conflict handling and forced PID cleanup.
- mount-path fallback logic for model/spool roots.
- legacy env compatibility mapping.

## Crawl scheduling and ingestion pathway

Primary scheduler entrypoint: `scripts/ops/run_crawl_schedule.py`

Flow:
1. Parse args and select schedule source (`config/crawl_schedule.yaml` or DB-derived source schedule).
2. Resolve due runs for current time window.
3. Build per-run crawler payload (domains, limits, strategy, overrides).
4. Submit job(s) to crawler endpoint and poll completion.
5. Aggregate run results and adaptive article metrics; write state/success artifacts.
6. Emit Prometheus textfile metrics for scheduler and throughput tracking.
7. Hand off downstream via crawler/memory/archive/orchestrator service interactions.

Branch pathways:
- `--dry-run`: planning-only no crawler invocation.
- `--testrun`: static schedule mode bypassing DB source expansion.
- profile override branches (`--profiles`, `--NoFollow`, timeout/max-target overrides).
- job timeout/error branch -> timeout/runtime error path with state logging for governance.

## Workflow orchestrator control-plane pathway

Entrypoint: `agents/workflow_orchestrator/main.py`

Active interfaces:
- health/status endpoints: `/health`, `/status`, `/autonomic/status`, `/metrics`
- runtime config APIs: GET/validate/apply/rollback/actuate endpoints for hot runtime policy controls
Lifecycle:
- startup attaches runtime store, starts engine loop, registers MCP tools with MCP bus, and serves control-plane endpoints.
- shutdown stops engine gracefully.
Branch pathways:
- runtime patch validation fail -> HTTP 400 with diagnostics.
- rollback to prior version path with owner-specific override extraction and re-apply.
- actuation tier patch path (tiered runtime controls) plus rollback route.

## Environment/test quality pathways

Active scripts:
- `scripts/bootstrap_venv.sh` (canonical environment setup)
- `scripts/dev/pytest.sh` (venv-first pytest launcher)
- `scripts/dev/run_full_pytest_safe.sh` (safe env full suite wrapper)
- `scripts/run_tests_with_env.sh` (preset-driven test env launcher)
- `scripts/dev/check_canonical_env.sh` (forbid active conda literals)

Branch pathways:
- if `.venv/bin/python` present -> direct python -m pytest; else `uv run`; else bare `pytest` fallback.
- test preset branches (`local`, `gpu`, `chroma-live`, `vllm`, `playwright`, `redis`, `all`).
- policy-fail branch in canonical env checker if legacy env literals appear in active paths.

## Operational control branches (memory governor)

Scripts: `scripts/ops/enable_governor.sh`, `scripts/ops/disable_governor.sh`, `scripts/ops/justnews_memory_governor.py`
Flow:
- enable script persists env thresholds, builds managed PID map from active service ports, starts governor daemon.
- disable script flips enable flag and terminates daemon process.
Branch pathways:
- python resolution branch: `/deps/.venv` -> project `.venv` -> `python3` fallback.
- managed process discovery branch based on service manifest + optional publisher process.
- threshold branch behavior controlled by soft/hard/emergency/resume and dwell/cooldown intervals.

## Indexing/tooling pathways

Primary scripts:
- `scripts/indexing/build_code_index.py` (incremental/full index build)
- `scripts/indexing/query_code_index.py` (index query)
- `scripts/indexing/index_autoupdate_daemon.sh` + timer/service examples
- Make targets (`index-*`) orchestrate install/enable/run-now/bootstrap/telemetry flows.

Branch pathways:
- systemd user bus available branch -> timer/service usage.
- no user bus branch -> daemon fallback script.
- full rebuild vs incremental update branch.

## Compatibility and retired-path safeguards

- Root retired scripts are compatibility stubs that now fail non-zero and point to `archive_local/` copies.
- Retired infrastructure generators (k8s/docker/helm script generators, legacy postgres setup) are archived with active-path stubs.
- Redirect index: `docs/operations/ROOT_LEGACY_REDIRECT_INDEX.md`.
- Archive policy: `docs/operations/DEPRECATED_ARCHIVE_POLICY.md`.

## Workflow branch matrix (summary)

| Workflow | Primary path | Branches / alternates |
|---|---|---|
| Service lifecycle | Docker compose wrapper (`docker_compose.sh`) via Makefile/wrappers | `JUSTNEWS_COMPOSE_FILE` override; direct compose subcommands; optional explicit systemd fallback |
| Crawl execution | `run_crawl_schedule.py` -> crawler jobs -> ingest | dry-run, testrun, DB/source schedule branch, profile override branch, timeout/error branch |
| Orchestrator policy control | `workflow_orchestrator` runtime APIs | validate failure branch, apply/rollback branch, tier actuation branch |
| Test execution | `pytest.sh` / `run_full_pytest_safe.sh` | .venv vs uv vs pytest fallback; preset branches in `run_tests_with_env.sh` |
| Env policy enforcement | `check_canonical_env.sh` | allowlist archival docs branch vs active path hard-fail branch |
| Memory pressure governance | `enable_governor.sh`/`disable_governor.sh` | python resolution branch, PID discovery branch, threshold policy branch |
| Code indexing | make `index-*` + indexing scripts | systemd user timer branch vs daemon fallback branch; incremental/full build branch |

## Known limitations of this audit

- This map is script-pathway centric; internal function-level call graphs inside every agent module are out-of-scope.
- Some scripts are active but currently unreferenced by Make/workflows (manual operator utilities). These remain listed in inventory JSON.
- Repository has a large historical surface; this document focuses on active operational pathways and branch points relevant to runtime/control workflows.

## Source artifacts

- `docs/operations/_script_audit_inventory.json` (full machine inventory + caller graph)
- `docs/architecture_overview.md` (system architecture context)
- `docs/operations/ROOT_LEGACY_REDIRECT_INDEX.md` (retired root script replacements)
