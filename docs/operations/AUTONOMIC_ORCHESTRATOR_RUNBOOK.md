# Autonomic Orchestrator Runbook

> Historical context note: This document may describe legacy startup/orchestration flows captured at the time. Canonical runtime for JustNews is Docker-first. See `docs/operations/DOCKER_FIRST_STRATEGY.md` and `docs/operations/DOCKER_CANONICAL_COMMANDS.md`.


Date: 2026-02-19  
Status: Validated via Incident Simulation (2026-02-19)

## Related Docs

- [../architecture/AUTONOMIC_ORCHESTRATOR_ARCHITECTURE.md](../architecture/AUTONOMIC_ORCHESTRATOR_ARCHITECTURE.md)
- [../architecture/AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md](../architecture/AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md)
- [../architecture/AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md](../architecture/AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md)
- [../architecture/LIVE_TUNING_CONTROL_PLANE_DESIGN.md](../architecture/LIVE_TUNING_CONTROL_PLANE_DESIGN.md)

## 1. Purpose

Provide operators with safe procedures to enable, monitor, troubleshoot, and rollback the Autonomic Orchestrator.

## 2. Operating Modes

- disabled: no autonomic actions
- shadow: decisions logged, no live writes
- active: bounded live writes enabled

## 3. Preconditions

- Runtime config API is healthy and reachable.
- Audit log persistence is available.
- Orchestrator status endpoint exposes applied config version.
- Baseline SLOs and alert thresholds are configured.

## 4. Standard Enablement Sequence

1. Verify services healthy.
2. Enable shadow mode.
3. Observe at least one full decision cycle window.
4. Review decision logs and guardrail outcomes.
5. Promote to active mode for canary scope only.
6. Validate canary metrics before wider rollout.

## 5. Required Monitoring Signals

- Pipeline throughput trend
- Queue depth trend by stage
- Per-policy success/failure rate
- MCP call failure and retry rates
- Fact-check latency and timeout trends
- Resource saturation (CPU/memory/GPU)
- Config propagation lag and apply failures

## 5.1 Throughput-First Reliable Control Profile

The orchestrator now supports a backlog-floor recovery action that restores bounded throughput when queue pressure rises and resources are still healthy.

Decision behavior:
- `resource_pressure`: reduce `max_concurrent_tasks`, increase `polling_interval_seconds`
- `downstream_stall_recovery`: increase `max_concurrent_tasks`, decrease `polling_interval_seconds`
- `queue_backlog_floor_recovery`: if backlog pressure is present and runtime settings are below throughput floor, restore floor values
- `stable_no_change`: no patch

Backlog-floor recovery guardrails:
- Only considered when resources are healthy and not under saturation pressure
- Uses the same damping streak logic as other actions (`AUTONOMIC_ACTION_STREAK_REQUIRED`)
- Uses existing cooldown and action-budget guardrails
- Uses existing runtime key allowlist/denylist and auto-rollback SLO protections

Recommended throughput-first, reliability-safe environment settings:
- `AUTONOMIC_QUEUE_RECOVERY_DEPTH=8`
- `AUTONOMIC_QUEUE_RECOVERY_PRESSURE_SCORE=10.0`
- `AUTONOMIC_THROUGHPUT_FLOOR_MAX_CONCURRENT_TASKS=3`
- `AUTONOMIC_THROUGHPUT_FLOOR_POLLING_INTERVAL_SECONDS=6`

Interpretation:
- Keep floor values moderate. Higher floors can improve drain speed but increase risk of contention.
- Keep dynamic per-policy controls enabled to absorb local bottlenecks while global floor drives end-to-end flow.
- If rollback events occur, lower floor task count first before widening cooldown or disabling active mode.

## 6. Incident Triggers and Immediate Actions

### Trigger: Error-rate spike

Immediate actions:
- Switch autonomic mode to shadow or disabled.
- Execute last-known-good rollback version.
- Confirm recovery of service error rates.

### Trigger: Throughput collapse with queue growth

Immediate actions:
- Disable active mode.
- Rollback latest configuration version.
- Check resource saturation and circuit-breaker states.

### Trigger: Resource saturation sustained

Immediate actions:
- Force rollback to prior stable version.
- Hold active mode until saturation clears.
- Re-enter shadow mode for diagnosis.

## 7. Rollback Procedure

1. Identify target rollback version.
2. Execute rollback through runtime config API.
3. Confirm applied version on orchestrator status endpoint.
4. Verify stabilization window (errors, throughput, queue depth).
5. Record rollback event in incident log.

## 8. Canary Progression Policy

- Stage 1: Dev only
- Stage 2: Small canary subset
- Stage 3: Expanded canary
- Stage 4: Full rollout

Advance only if all are true for two consecutive windows:
- Error-rate within threshold
- Throughput not regressed beyond gate
- Queue depth stable or improving
- No critical alert on config propagation/apply failures

## 9. Operator Checklist

- [ ] Mode and scope documented before change
- [ ] Pre-change baseline captured
- [ ] Change reason recorded
- [ ] Post-change verification completed
- [ ] Rollback readiness confirmed
- [ ] Incident notes updated (if applicable)

### 9.1 Throughput Validation Checklist

- [ ] Capture pre-change baseline: queue depth, effective poll interval, effective max concurrent tasks
- [ ] Enable backlog-floor settings and keep autonomic mode in `active` only for canary scope
- [ ] Verify `/status` decision tail includes `queue_backlog_floor_recovery` when backlog is present
- [ ] Verify no sustained increase in tick error rate or repeated auto-rollbacks
- [ ] Confirm queue depth trend decreases faster than baseline over equivalent window
- [ ] Record final accepted floor settings and decision evidence in ops notes

## 10. Post-Incident Review Template

- Incident start/end:
- Trigger signal:
- Autonomic mode at incident start:
- Last applied config version:
- Rollback version used:
- Time to stabilization:
- Root cause summary:
- Follow-up actions:

## 11. Cross-References

- docs/architecture/AUTONOMIC_ORCHESTRATOR_ARCHITECTURE.md
- docs/architecture/AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md
- docs/architecture/AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md
- docs/architecture/LIVE_TUNING_CONTROL_PLANE_DESIGN.md
