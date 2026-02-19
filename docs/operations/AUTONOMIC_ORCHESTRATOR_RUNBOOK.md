# Autonomic Orchestrator Runbook

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
