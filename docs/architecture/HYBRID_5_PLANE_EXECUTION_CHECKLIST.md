# Hybrid 5-Plane Topology — Execution Checklist

> Historical context note: This document may describe legacy startup/orchestration flows captured at the time. Canonical runtime for JustNews is Docker-first. See `docs/operations/DOCKER_FIRST_STRATEGY.md` and `docs/operations/DOCKER_CANONICAL_COMMANDS.md`.


Date: 2026-02-17  
Source plan: [HYBRID_5_PLANE_REFACTOR_PLAN.md](HYBRID_5_PLANE_REFACTOR_PLAN.md)

## Goal

Execute the hybrid 5-plane migration with strict focus on:
- **Accuracy** (deterministic routing/config)
- **Robustness** (bounded failure blast radius)
- **Speed** (no unnecessary latency/startup regressions)

---

## Plane Model (Reference)

- **Plane A Foundation**: mariadb, chromadb, redis, vllm, mcp_bus
- **Plane B Control**: workflow_orchestrator, gpu_orchestrator, crawler_control
- **Plane C Data/IO**: crawler, memory, fact-check backend
- **Plane D Editorial Compute**: chief_editor, analyst, synthesizer, critic, reasoning, newsreader, journalist
- **Plane E Presentation/Support**: dashboard, analytics, archive, HITL/support

---

## Phase 0 — Alignment & Freeze

### Checklist
- [ ] Confirm canonical service list + ports match across:
  - [ ] [infrastructure/agents_manifest.sh](../../infrastructure/agents_manifest.sh)
  - [ ] [docs/canonical_port_mapping.md](../canonical_port_mapping.md)
  - [ ] [start_all_services.sh](../../start_all_services.sh)
- [ ] Record approved plane membership map in docs.
- [ ] Freeze non-goals (no API contract changes, no schema redesign).

### Exit Criteria
- [ ] One approved source of truth for identity/ports/startup order.

---

## Phase 1 — Plane-Ordered Startup + Health Gates

### Checklist
- [ ] Refactor [start_all_services.sh](../../start_all_services.sh) into explicit plane sections (A→E).
- [ ] Implement gate functions (`require_plane_ready` style) for hard dependencies.
- [ ] Define hard-blocking vs soft-degraded behavior by plane.
- [ ] Add concise per-plane startup summary output.
- [ ] Keep existing flags behavior (`--skip-*`, `--dry-run`) intact.

### Validation
- [ ] `--dry-run` shows deterministic A→E ordering.
- [ ] Startup aborts on Plane A/B hard gate failures.
- [ ] Startup continues in degraded mode for Plane E failures.

---

## Phase 2 — Foundation + Control Hardening

### Checklist
- [ ] Standardize readiness probes for Plane A services.
- [ ] Align probe semantics between devcontainer and startup scripts.
- [ ] Add/normalize readiness checks for Plane B services.
- [ ] Ensure control-plane readiness before Plane C starts.
- [ ] Verify restart behavior does not require full-system recycle.

### Validation
- [ ] Plane A recovers cleanly from individual service restarts.
- [ ] Plane B restart does not destabilize Plane A.
- [ ] mcp_bus registration recovery works after bus restart.

---

## Phase 3 — Data/IO Reliability

### Checklist
- [ ] Formalize fact-check shim/backend contract and timeout boundaries.
- [ ] Standardize retries/backoff/circuit behavior for `crawler` and `memory`.
- [ ] Enforce idempotent write semantics where available.
- [ ] Add explicit error-state handling for failed write paths.

### Validation
- [ ] Failure in one Data/IO service does not cascade to Plane A/B outage.
- [ ] Fact-check path behavior is deterministic under transient failures.

---

## Phase 4 — Editorial Compute Throughput

### Checklist
- [ ] Keep Plane D as shared worker pool (no broad one-container-per-agent split).
- [ ] Tune concurrency and timeout defaults for shared vLLM.
- [ ] Reduce unnecessary startup serialization in Plane D.
- [ ] Confirm all editorial agents use centralized inference endpoint.

### Validation
- [ ] No per-agent model duplication introduced.
- [ ] Editorial p95 latency stable/improved vs baseline.

---

## Phase 5 — Presentation/Support Non-Blocking Policy

### Checklist
- [ ] Mark Plane E as non-blocking for core publish path.
- [ ] Ensure startup reports Plane E degraded state without blocking A–D.
- [ ] Update operator runbooks to reflect degraded behavior.

### Validation
- [ ] Core workflow remains healthy with Plane E intentionally stopped.

---

## Phase 6 — Rollout, Metrics, Sign-off

### Checklist
- [ ] Capture before/after baselines:
  - [ ] Total startup time
  - [ ] Per-plane readiness time
  - [ ] p95 latency (core endpoints)
  - [ ] Recovery time after forced restart
  - [ ] Error rate by plane
- [ ] Update integration tests and startup verification scripts.
- [ ] Run staged rollout (devcontainer → integration env → operator runbook).
- [ ] Approve final sign-off report.

### Exit Criteria
- [ ] Accuracy targets met.
- [ ] Robustness targets met.
- [ ] Speed targets met.

---

## Hard Decision Guardrails

- [ ] Keep **single centralized vLLM** endpoint.
- [ ] Do not adopt full per-agent containerization in this migration.
- [ ] Isolate only high-value services first (control + data/IO heavy paths).
- [ ] Treat deprecated Docker/Helm artifacts as non-target unless reactivated intentionally.

---

## Rollback Triggers

Trigger rollback to previous startup mode if any occur:
- [ ] Repeated startup gate deadlocks
- [ ] p95 latency regression above agreed threshold
- [ ] Recovery-time regression above agreed threshold
- [ ] Cross-plane cascading failures in normal restart tests

Rollback assets:
- [ ] Prior startup script path preserved behind feature flag
- [ ] Previous runbook steps retained until Phase 6 sign-off

---

## Operator Command Pack (Minimal)

- [ ] Dry-run topology sequence: `./start_all_services.sh --dry-run`
- [ ] Standard startup: `./start_all_services.sh`
- [ ] Health verification: `./infrastructure/systemd/scripts/health_check.sh -v`
- [ ] Service-specific logs: `journalctl -u justnews@<agent> -f`

---

## Ownership Template (Fill In)

- **Architecture Owner**: [ ]
- **Runtime/Infra Owner**: [ ]
- **Data/IO Owner**: [ ]
- **Editorial Plane Owner**: [ ]
- **Ops/Runbook Owner**: [ ]
- **Performance Validation Owner**: [ ]

---

## Final Go/No-Go

- [ ] All phase exit criteria met
- [ ] No P1/P0 open issues
- [ ] Docs updated and consistent
- [ ] Rollback tested
- [ ] Go-live approved
