# Docker-First Cutover Implementation Plan

For Hermes: execute this plan in small, reversible increments. Keep systemd app orchestration backward-compatible during transition, then retire once Docker runtime is validated.

Goal
- Make Docker Compose the canonical runtime for JustNews app services in near-term production/dev while retaining systemd only as optional host wrapper.
- Prepare a clean migration runway to Kubernetes later.

Architecture
- Phase 1 (now): Docker-first runtime and docs alignment, minimal compatibility shims, no hard deletion of systemd.
- Phase 2: Move service lifecycle/health/restart semantics into compose-native patterns.
- Phase 3: Introduce k8s-ready conventions (statelessness, readiness/liveness contracts, secret strategy) and optional k8s manifests/charts.

Tech stack
- Docker Compose
- Python/UV .venv for local non-container workflows
- Existing JustNews scripts and Make targets

---

## Phase 1 (Begin now) — Docker canonicalization without hard break

Task 1: Define canonical policy docs
- Create/Update:
  - docs/operations/DOCKER_FIRST_STRATEGY.md
  - infrastructure/README.md
  - docs/DOCUMENTATION_INDEX.md
- Outcome:
  - Docker-first declared canonical runtime.
  - systemd re-scoped as optional host wrapper and legacy app-orchestrator path.

Task 2: Add Docker lifecycle command surface
- Create:
  - scripts/ops/docker_compose.sh
- Update:
  - Makefile with docker lifecycle targets
- Outcome:
  - Stable, scriptable entrypoints:
    - make deploy-docker
    - make deploy-docker-stop
    - make deploy-docker-status
    - make deploy-docker-logs

Task 3: Make development deploy target Docker-first
- Update Makefile deploy-development target to call deploy-docker (while keeping systemd targets available).

Task 4: Keep strict guardrails
- Retired-root stub hard-block test remains in CI.
- Canonical env checker continues to pass.

## Phase 2 — Runtime parity hardening

Task 5: Compose health/restart parity
- Ensure all core services have healthchecks and restart policies.
- Add dependency ordering with health conditions.

Task 6: Env/secrets normalization
- Standardize env-file strategy for compose runtime.
- Minimize host-path assumptions in service startup scripts.

Task 7: Ops runbook parity
- Add Docker-first production runbook with:
  - startup/shutdown/restart
  - logs/metrics/debug
  - rollback and disaster-recovery quick steps

## Phase 3 — Kubernetes readiness

Task 8: K8s compatibility checklist
- Add readiness contract doc and per-service checklist.
- Identify stateful vs stateless boundaries.

Task 9: Migration scaffolding
- Add initial manifests/chart skeletons (no immediate cutover).
- Keep Compose as source-of-truth for image/runtime contracts during transition.

## Acceptance criteria

- Docker-first strategy documented and linked in index docs.
- Makefile exposes docker deployment lifecycle targets.
- deploy-development defaults to Docker path.
- No break in existing compatibility scripts.
- scripts/dev/check_canonical_env.sh passes.

## Rollback strategy

- Keep systemd scripts/units in place during Phase 1.
- Docker-first changes are additive or shallow-routing only.
- Revert Makefile routing if required without data migration.
