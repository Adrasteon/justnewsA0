# Autonomic Orchestrator Implementation Plan

Date: 2026-02-19  
Status: Approved for Execution

## Related Docs

- [AUTONOMIC_ORCHESTRATOR_ARCHITECTURE.md](AUTONOMIC_ORCHESTRATOR_ARCHITECTURE.md)
- [AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md](AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md)
- [../operations/AUTONOMIC_ORCHESTRATOR_RUNBOOK.md](../operations/AUTONOMIC_ORCHESTRATOR_RUNBOOK.md)
- [LIVE_TUNING_CONTROL_PLANE_DESIGN.md](LIVE_TUNING_CONTROL_PLANE_DESIGN.md)

## Scope and Fixed Decisions

- Scope: Full end-state Autonomic Orchestrator plan
- Runtime config source-of-truth: New runtime config store/API first
- Workflow orchestrator canonical port: 8023

## Goal

Deliver a safe, auditable autonomic control loop for JustNews that can sense system state, make bounded decisions, apply reversible runtime actions, and improve policy choices over time without destabilizing production.

## Success Criteria

- Runtime config changes are versioned, validated, and rollback-capable.
- Orchestrator applies supported hot-reload settings within 5 seconds.
- Autonomic actions stay within safety envelopes and are fully audited.
- No unbounded regressions in throughput, latency, or error rates during canary/rollout.

## Execution Phases

### Phase 1 — Foundation and Drift Cleanup

- [ ] Align workflow orchestrator references to port 8023 across docs/config/runtime mappings.
- [ ] Resolve policy naming drift (`AnalysisToFactCheckPolicy` naming consistency).
- [ ] Fix override expiry reliability path in orchestrator policy utilities.
- [ ] Add baseline observability snapshot and regression guardrails.

Exit Criteria:
- [ ] No conflicting port/policy references remain in canonical paths.
- [ ] Existing orchestrator code compiles and baseline health/status remains green.

### Phase 2 — Runtime Control Plane Prerequisites

- [ ] Implement versioned runtime config read/validate/apply API.
- [ ] Define mutability contracts (`hot` vs `restart_required`) and enforce validation.
- [ ] Add audit log entries for every config write/rollback.
- [ ] Implement rollback endpoint and target-version restore.

Exit Criteria:
- [ ] Config writes are atomic and versioned.
- [ ] Invalid updates are rejected pre-apply.
- [ ] Rollback restores prior effective values.

### Phase 3 — Orchestrator Sensing Integration

- [ ] Add periodic config-version check and apply cycle in orchestrator engine.
- [ ] Add per-policy telemetry capture (queue depth, success/fail, latency).
- [ ] Add resource and downstream stall signals to sensing state.
- [ ] Expose applied config version and autonomic status via status endpoints.

Exit Criteria:
- [ ] Orchestrator reports effective version and last apply result.
- [ ] Sensing metrics available for decision inputs.

### Phase 4 — Decision Engine (Safe-First)

- [ ] Implement deterministic rule-based controller with bounded action space.
- [ ] Add cooldowns, budgets, guardrails, and denylist for unsafe knobs.
- [ ] Add explainability payload for each decision (why/action/expected impact).
- [ ] Add feature flag for enabling autonomic decisions.

Exit Criteria:
- [ ] Decisions are reproducible and bounded.
- [ ] Every decision is explainable and auditable.

### Phase 5 — Actuation and Reversibility

- [ ] Implement Tier-1 actuation (orchestrator polling/concurrency/resource thresholds).
- [ ] Implement Tier-2 actuation (MCP timeout/retry/circuit thresholds).
- [ ] Implement Tier-3 actuation (fact-check query/deep-crawl runtime knobs).
- [ ] Ensure each action has inverse rollback operation.

Exit Criteria:
- [ ] Supported actions apply without restart.
- [ ] Rollback paths are verified for all supported actions.

### Phase 6 — Learning Layer and Hardening

- [ ] Start with shadow-mode scoring (no live changes) to validate signal quality.
- [ ] Add optional contextual-bandit optimizer behind feature flag.
- [ ] Add SLO-driven auto-rollback triggers.
- [ ] Add propagation lag, apply-failure, and staleness alerts.

Exit Criteria:
- [ ] Shadow mode demonstrates stable policy quality.
- [ ] Live mode canary passes without SLO regressions.

### Phase 7 — Canary and Production Rollout

- [ ] Run staged rollout (dev → canary subset → full).
- [ ] Track throughput/latency/error deltas at each gate.
- [ ] Execute rollback drills before full rollout approval.
- [ ] Publish operations handoff and on-call playbook.

Exit Criteria:
- [ ] Canary and full rollout gates passed.
- [ ] Runbook validated by at least one incident simulation.

## Monitoring Board

Use this section to track execution status during implementation.

| Phase | Owner | Start Date | Target Date | Status | Evidence Link |
|---|---|---|---|---|---|
| 1 Foundation |  | 2026-02-19 |  | In Progress | docs/operations/AUTONOMIC_ORCHESTRATOR_PHASE1_BASELINE_2026-02-19.md |
| 2 Control Plane |  | 2026-02-19 | 2026-02-19 | Completed | docs/operations/AUTONOMIC_ORCHESTRATOR_PHASE2_VERIFICATION_2026-02-19.md |
| 3 Sensing |  | 2026-02-19 | 2026-02-19 | Completed | docs/operations/AUTONOMIC_ORCHESTRATOR_PHASE3_VERIFICATION_2026-02-19.md |
| 4 Decision Engine |  | 2026-02-19 | 2026-02-19 | Completed | docs/operations/AUTONOMIC_ORCHESTRATOR_PHASE4_VERIFICATION_2026-02-19.md |
| 5 Actuation |  | 2026-02-19 | 2026-02-19 | Completed | docs/operations/AUTONOMIC_ORCHESTRATOR_PHASE5_VERIFICATION_2026-02-19.md |
| 6 Learning/Hardening |  | 2026-02-19 |  | In Progress | docs/operations/AUTONOMIC_ORCHESTRATOR_PHASE6_KICKOFF_2026-02-19.md |
| 7 Rollout |  |  |  | Not Started |  |

## Risk Register

- Risk: Over-tuning causes oscillation
  - Mitigation: Cooldowns, change budgets, and write-rate limits
- Risk: Partial adoption creates inconsistent behavior
  - Mitigation: Version visibility, apply acknowledgements, unsupported-key errors
- Risk: Runtime config store outage
  - Mitigation: Last-known-good cache and staleness alerts

## Change Log

- 2026-02-19: Initial plan created with execution phases and monitoring board.
- 2026-02-19: Phase 1 implementation started; baseline observability snapshot and regression guardrails recorded.
- 2026-02-19: Phase 2 started with versioned runtime config API scaffolding (validate/apply/rollback) and orchestrator live apply wiring.
- 2026-02-19: Phase 2 completed with mutability-enforced runtime apply, rollback restore verification, and evidence artifact.
- 2026-02-19: Phase 3 completed with per-tick runtime sync, per-policy telemetry capture, resource/stall signals, and enriched status payloads.
- 2026-02-19: Phase 4 completed with deterministic safe-first decision engine, guardrails/denylist enforcement, explainability payloads, and mode/feature-flag controls.
- 2026-02-19: Phase 5 completed with Tier-1/2/3 actuation wiring and inverse rollback-by-action verification.
- 2026-02-19: Phase 6 started with shadow-mode learning telemetry, bandit-gated optimization state, SLO auto-rollback hooks, and runtime staleness/apply-failure alerts.
