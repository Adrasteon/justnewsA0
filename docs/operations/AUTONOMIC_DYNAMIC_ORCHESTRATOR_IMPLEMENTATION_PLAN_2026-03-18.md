# Autonomic Dynamic Orchestrator Implementation Plan

Date: 2026-03-18
Owner: Ops + Workflow Orchestrator
Status: Active canary validated (E2 complete; preparing E3 promotion)

## Objective

Evolve the existing autonomic governor from shadow, low-scope control into a fully real-time dynamic workflow orchestrator that:

- Maximizes sustained backlog drain.
- Preserves reliability and recovery guarantees.
- Produces explainable decisions with bounded blast radius.

## Current Baseline

- Mode: `AUTONOMIC_MODE=active`
- Decisions: enabled
- Learning: enabled
- Bandit: disabled
- Actuation scope:
  - `orchestrator.polling_interval_seconds`, `orchestrator.max_concurrent_tasks`
  - Per-policy dynamic pull limits (C2, bounded)
  - Per-policy dynamic execution parallelism (C3, bounded)

Key active canary traits:

- Conservative cooldown and action budget remain enabled.
- Scheduler path: pressure-weighted plus fairness budget.
- Reliability in recent windows: no MySQL disconnect and no analyst 500 marker increase.

## Implementation Status (As Of 2026-03-18)

Completed:

- A2: decision reason taxonomy in engine decision payloads.
- A3: richer decision trace payloads exposed through status endpoints.
- B1: queue-pressure state vector and status exposure.
- B2: pressure-weighted scheduler behind feature flag.
- B3: deficit-based fairness budget across policies.
- C2: conservative dynamic per-policy pull limit controller.
- C3: conservative dynamic per-policy execution parallelism controller.
- C4 (initial): anti-oscillation damping for decision proposals.
- D3: canary scorecard script and documentation.
- E1: active canary observation and repeatability validation.
- E2: rollback drill pass and auto-rollback enablement.

In progress:

- E3: wider promotion planning and staged rollout criteria.

Pending:

- C1 (expanded allowlist), D1, D2, E3.

## Operational Evidence (2026-03-18)

### E2 rollback drill (passed)

- Baseline runtime values before drill:
  - `polling_interval_seconds=5`
  - `max_concurrent_tasks=7`
- Controlled apply action:
  - reason: `e2_drill_apply_for_rollback_validation_clean`
  - result: `status=ok`, `version=376`
  - observed runtime after apply: `polling_interval_seconds=4`, `max_concurrent_tasks=7`
- Apply-version rollback:
  - reason: `e2_drill_rollback_validation_clean`
  - result: `status=ok`, `inverse_of_apply_version=376`
  - observed runtime after rollback: `polling_interval_seconds=5`, `max_concurrent_tasks=7`

### Auto-rollback enablement (completed)

- `global.env` set to `AUTONOMIC_AUTO_ROLLBACK_ENABLED=1`.
- Workflow orchestrator restarted and verified on `/autonomic/status`:
  - `mode=active`
  - `auto_rollback_enabled=true`

### Post-enable gate outcomes

15-minute gate (`baseline -> t15m`):

- `analyzed_delta=32`
- `backlog_drain=32`
- `mysql_disconnect_delta=0`
- `analyst_500_delta=0`
- verdict: `GO`

60-minute gate (`baseline -> t60m`):

- `analyzed_delta=52`
- `backlog_drain=52`
- `mysql_disconnect_delta=0`
- `analyst_500_delta=0`
- scheduler mode: `weighted+fairness`
- verdict: `GO`

## Current Canary Runtime Knobs (C2/C3)

The following knobs are currently active in `global.env` for conservative policy-level control.

| Variable | Current Value | Intent |
|---|---:|---|
| `ORCH_DYNAMIC_POLICY_LIMITS_ENABLED` | `1` | Enable C2 dynamic pull limits |
| `ORCH_DYNAMIC_POLICY_LIMIT_UP_DELTA` | `1` | Allow at most +1 above static limit cap |
| `ORCH_DYNAMIC_POLICY_LIMIT_DOWN_DELTA` | `1` | Allow at most -1 below static limit cap |
| `ORCH_DYNAMIC_POLICY_LIMIT_COOLDOWN_SECONDS` | `120` | Minimum seconds between limit adjustments |
| `ORCH_DYNAMIC_POLICY_LIMIT_SCALE_UP_QUEUE_DEPTH` | `4` | Queue depth trigger for scale-up consideration |
| `ORCH_DYNAMIC_POLICY_LIMIT_SCALE_DOWN_QUEUE_DEPTH` | `0` | Queue depth trigger for scale-down consideration |
| `ORCH_DYNAMIC_POLICY_LIMIT_MAX_ERROR_RATE` | `0.20` | Block scale-up above this error-rate threshold |
| `ORCH_DYNAMIC_POLICY_LIMIT_RECENT_ERROR_COOLDOWN_SECONDS` | `180` | Treat recent errors as temporary scale-up guardrail |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_ENABLED` | `1` | Enable C3 dynamic execution parallelism |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_UP_DELTA` | `1` | Allow at most +1 above static parallelism cap |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_DOWN_DELTA` | `1` | Allow at most -1 below static parallelism cap |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_COOLDOWN_SECONDS` | `180` | Minimum seconds between parallelism adjustments |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_SCALE_UP_QUEUE_DEPTH` | `6` | Queue depth trigger for parallelism scale-up consideration |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_SCALE_DOWN_QUEUE_DEPTH` | `0` | Queue depth trigger for parallelism scale-down consideration |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_MAX_ERROR_RATE` | `0.20` | Block parallelism scale-up above this error-rate threshold |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_RECENT_ERROR_COOLDOWN_SECONDS` | `180` | Treat recent errors as temporary parallelism scale-up guardrail |
| `ORCH_DYNAMIC_POLICY_PARALLELISM_ABSOLUTE_MAX` | `4` | Hard absolute parallelism ceiling |

Core implementation files:

- `agents/workflow_orchestrator/engine.py`
- `agents/workflow_orchestrator/policies.py`
- `agents/workflow_orchestrator/main.py`
- `agents/workflow_orchestrator/tools.py`
- `global.env`

## Delivery Phases

1. Phase A: Control-plane hardening and objective formalization.
2. Phase B: Real-time state model and pressure-aware scheduling.
3. Phase C: Expanded actuation scope with strict guardrails.
4. Phase D: Shadow perturbation training and canary rollout.
5. Phase E: Active-mode promotion with auto-rollback.

## Implementation Backlog

| ID | Task | Primary Files | Deliverable | Acceptance Criteria |
|---|---|---|---|---|
| A1 | Define controller scorecard and SLO guardrails | `docs/operations/AUTONOMIC_DYNAMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN_2026-03-18.md`, `docs/operations/INGESTION_TO_ANALYSIS_REMEDIATION_LOG.md` | Fixed KPI/SLO contract | Throughput, stall, error-rate, and rollback triggers are explicit and measurable |
| A2 | Add explicit decision-reason taxonomy | `agents/workflow_orchestrator/engine.py` | Structured reason codes | Every decision emits one canonical reason code and expected effect |
| A3 | Add decision trace payloads to API | `agents/workflow_orchestrator/tools.py`, `agents/workflow_orchestrator/main.py` | Rich status payload | `/autonomic/status` includes rationale, rejected actions, and confidence fields |
| B1 | Build queue-pressure state vector | `agents/workflow_orchestrator/engine.py` | Multi-signal state snapshot | State includes queue depth, queue age, success/error trend, latency trend |
| B2 | Add pressure-weighted scheduler | `agents/workflow_orchestrator/engine.py` | Dynamic policy ordering per tick | No starvation under mixed load; scheduling rationale included in telemetry |
| B3 | Add fairness budget across policies | `agents/workflow_orchestrator/engine.py` | Deficit/fairness accounting | Heavy stages cannot permanently starve downstream policies |
| C1 | Expand allowlisted runtime knobs (phase-gated) | `agents/workflow_orchestrator/engine.py`, `config/runtime/*` | Additional safe actuation keys | Keys are min/max clamped and denylist-protected |
| C2 | Add per-policy dynamic limit control | `agents/workflow_orchestrator/engine.py` | Runtime control for policy pull limits | Limits adjust from live state and remain within guardrails |
| C3 | Add per-policy dynamic execution parallelism control | `agents/workflow_orchestrator/policies.py`, `agents/workflow_orchestrator/engine.py` | Runtime control for execution fan-out | Parallelism adapts with low error rates and bounded queue latency |
| C4 | Add anti-oscillation damping | `agents/workflow_orchestrator/engine.py` | Hysteresis and rate-limit on knob changes | Repeated up/down thrashing is prevented in consecutive windows |
| D1 | Add controlled perturbation harness | `scripts/ops/`, `docs/operations/` | Repeatable shadow training drills | Shadow decisions include non-noop proposals across pressure/stall scenarios |
| D2 | Add shadow dataset export for analysis | `agents/workflow_orchestrator/engine.py`, `scripts/ops/` | Exportable decision/metric traces | Traces can be replayed and compared with fixed baselines |
| D3 | Add canary scorecard script | `scripts/ops/`, `docs/operations/MONITORING_SCRIPTS_REFERENCE.md` | 15/60-minute comparable reports | Automatic before/after summaries with same metric schema |
| E1 | Enable active mode in bounded canary | `global.env` | Active canary runbook settings | No SLO breach during canary windows; rollback path validated |
| E2 | Enable auto-rollback after canary pass | `global.env`, `agents/workflow_orchestrator/engine.py` | Autonomous protection in active mode | Forced fault drill triggers rollback deterministically |
| E3 | Promote to wider active scope | `global.env`, `docs/operations/*` | Production-ready controller profile | Sustained throughput uplift with stable error profile |

## Prioritized Build Queue (Ordered)

1. A2 (Decision reason taxonomy)
2. A3 (Decision trace payloads)
3. B1 (Queue-pressure state vector)
4. B2 (Pressure-weighted scheduler)
5. B3 (Fairness budget)
6. C2 (Per-policy dynamic limit control)
7. C3 (Per-policy dynamic execution parallelism)
8. C4 (Anti-oscillation damping)
9. C1 (Allowlist expansion, phase-gated)
10. D1 (Perturbation harness)
11. D2 (Shadow dataset export)
12. D3 (Canary scorecard script)
13. E1 (Active canary)
14. E2 (Auto-rollback promotion)
15. E3 (Wider rollout)

Rationale for this order:

- First make decisions observable and explainable before increasing control power.
- Add dynamic state awareness before introducing dynamic scheduling.
- Add policy-level controls only after scheduler and guardrails are measurable.

## Effort Estimates

| ID | Effort | Notes |
|---|---|---|
| A2 | 0.5 day | Low-risk engine-only telemetry improvement |
| A3 | 0.5 day | API/status payload extensions |
| B1 | 1 day | New state extraction and telemetry fields |
| B2 | 1.5 days | Scheduler behavior change and tuning |
| B3 | 1 day | Fairness counters and starvation protection |
| C2 | 1 day | Dynamic limit controller with clamps |
| C3 | 1 day | Dynamic fan-out controller in policies |
| C4 | 0.5 day | Hysteresis/rate-limit stabilization |
| C1 | 0.5 day | Registry/allowlist expansion and bounds |
| D1 | 1 day | Controlled perturbation scripts |
| D2 | 0.5 day | Shadow trace export pipeline |
| D3 | 0.5 day | Standardized canary scorecard |
| E1 | 0.5 day | Canary rollout and checkpointing |
| E2 | 0.5 day | Auto-rollback enablement drill |
| E3 | 1 day | Rollout hardening and documentation |

Estimated total: 11-12 engineering days plus canary observation windows.

## First 2-Day Sprint Cut

Day 1 scope:

1. A2: decision reason taxonomy in `engine.py`.
2. A3: decision trace payload fields exposed via status endpoints.
3. B1 (part 1): queue-pressure state extraction and status exposure.

Day 2 scope:

1. B1 (part 2): add queue-pressure summary to decision inputs.
2. B2 (initial): introduce opt-in pressure-weighted policy ordering behind feature flag.
3. C4 (initial): add minimal anti-oscillation damping for action proposals.

End-of-sprint acceptance gate:

1. `/autonomic/status` includes reason taxonomy, confidence, candidate/rejected actions, and queue-pressure state.
2. Shadow decisions remain stable with no regression in policy execution.
3. New scheduler path is feature-flagged and disabled by default.

## File-Level Task Breakdown

### `agents/workflow_orchestrator/engine.py`

- Add queue-age and queue-derivative tracking per policy.
- Add scheduling priority score function:
  - queue pressure
  - staleness
  - downstream blocking weight
  - error/latency penalties
- Add anti-oscillation hysteresis and bounded step sizes.
- Expand decision payload with:
  - candidate actions
  - rejected actions and guardrail reasons
  - expected gain estimate
- Add phase-gated allowlist expansion for policy-level knobs.

### `agents/workflow_orchestrator/policies.py`

- Add runtime-adjustable parallelism hooks per policy.
- Expose observed execution latency and outcome stats back to engine telemetry.
- Add bounded in-flight refill behavior for long-running stages.

### `agents/workflow_orchestrator/tools.py` and `agents/workflow_orchestrator/main.py`

- Extend `/autonomic/status` and `/status` to include:
  - current controller phase
  - last rejected actions
  - confidence and predicted impact fields
  - actuation budget consumption

### `global.env`

- Add explicit canary profile block (see below).
- Keep rollback profile block adjacent for rapid operator reversion.

### `scripts/ops/`

- Add perturbation drill scripts and canary scorecard scripts.
- Add repeatable report generation for 15-minute and 60-minute windows.

## First Canary Parameter Defaults

Use these defaults for first active canary windows after Phase A-C implementation is complete.

```dotenv
# Autonomic canary profile (first active pass)
AUTONOMIC_MODE=active
AUTONOMIC_DECISIONS_ENABLED=1
AUTONOMIC_LEARNING_ENABLED=1
AUTONOMIC_BANDIT_ENABLED=0
AUTONOMIC_AUTO_ROLLBACK_ENABLED=0

AUTONOMIC_DECISION_COOLDOWN_SECONDS=120
AUTONOMIC_DECISION_BUDGET_WINDOW_SECONDS=600
AUTONOMIC_MAX_ACTIONS_PER_WINDOW=2
AUTONOMIC_SHADOW_SCORE_WINDOW=180

AUTONOMIC_STALL_THRESHOLD_SECONDS=240
AUTONOMIC_SLO_MAX_TICK_ERROR_RATE=0.10
AUTONOMIC_SLO_MAX_STALL_SECONDS=600
AUTONOMIC_ALERT_STALENESS_SECONDS=180
AUTONOMIC_ALERT_PROPAGATION_LAG_SECONDS=5
```

Conservative first-actuation bounds:

- `orchestrator.polling_interval_seconds`: min `2`, max `4` during canary.
- `orchestrator.max_concurrent_tasks`: min `8`, max `12` during canary.
- Single-step delta per decision: `+/-1` only.

## Rollback Profile Defaults

```dotenv
# Immediate rollback profile
AUTONOMIC_MODE=shadow
AUTONOMIC_DECISIONS_ENABLED=1
AUTONOMIC_LEARNING_ENABLED=1
AUTONOMIC_BANDIT_ENABLED=0
AUTONOMIC_AUTO_ROLLBACK_ENABLED=0
```

## Canary Run Protocol

1. Run baseline window in shadow mode for 15 minutes.
2. Switch to active canary profile and restart orchestrator only.
3. Run 15-minute and 60-minute windows with fixed scorecard.
4. Compare throughput and reliability vs baseline.
5. Revert to rollback profile immediately on breach.

## Promotion And Rollback Runbook (Operator)

Standard canary command sequence:

1. Run gate window:
  - `/tmp/aw4_gate/run_gate.sh`
2. Score window:
  - `/deps/.venv/bin/python scripts/ops/canary_scorecard.py --dir /tmp/aw4_gate --start baseline --end t15m`
3. Record verdict and archive checkpoint files.

Recommended promotion rule (active canary -> promoted canary envelope):

- Require at least 3 consecutive `GO` scorecards.
- Require all of the following per window:
  - `analyzed_delta >= 1`
  - `backlog_drain >= 1`
  - `mysql_disconnect_delta <= 0`
  - `analyst_500_delta <= 0`

Immediate rollback triggers:

- Any scorecard `NO_GO` driven by reliability regressions.
- Consecutive windows with reliability regressions even if throughput improves.
- Manual operator judgment on instability (for example repeated oscillation or sustained stalls).

Rollback action:

1. Set rollback profile in `global.env`.
2. Restart workflow orchestrator only.
3. Re-run gate plus scorecard and confirm stability.

## Go/No-Go Gates

Go:

- Throughput uplift is repeatable across at least 3 windows.
- No sustained increase in timeout/error bursts.
- No policy starvation and no prolonged downstream stall.

No-Go:

- Oscillation across consecutive windows.
- Throughput uplift not repeatable.
- Any breach of hard rollback triggers.

## Immediate Next Steps

1. Prepare E3 staged promotion envelope and explicit rollback thresholds for each stage.
2. Complete C1 allowlist expansion with bounded clamps and denylist validation.
3. Build D1 perturbation harness for repeatable stress scenarios under active mode.
4. Build D2 shadow trace export to support replay-based tuning and auditability.
