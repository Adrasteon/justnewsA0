# Autonomic Orchestrator Architecture

Date: 2026-02-19  
Status: Proposed (Execution-Ready)

## Related Docs

- [AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md](AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md)
- [AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md](AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md)
- [../operations/AUTONOMIC_ORCHESTRATOR_RUNBOOK.md](../operations/AUTONOMIC_ORCHESTRATOR_RUNBOOK.md)
- [LIVE_TUNING_CONTROL_PLANE_DESIGN.md](LIVE_TUNING_CONTROL_PLANE_DESIGN.md)

## 1. Objective

Define the end-state architecture for a safe, auditable autonomic control system that continuously optimizes JustNews workflow performance while preserving reliability and operator control.

## 2. Scope

In scope:
- Sense → Decide → Act → Learn closed loop
- Runtime config control plane integration (versioned, validated, rollback-capable)
- Cross-service bounded actuation (orchestrator, MCP bus, fact checker)
- Operational safety gates, explainability, and auditability

Out of scope (for hot runtime mutation):
- Worker counts
- Model identity/quantization
- Port bindings
- Process-level CUDA startup parameters

## 3. Guiding Principles

1. Safety before optimization
2. Bounded action space only
3. Atomic and reversible changes
4. Clear human override and emergency stop
5. Full decision and action traceability

## 4. System Components

### 4.1 Autonomic Control Plane

- Runtime Config API
  - Validate, apply, and rollback versioned config patches
- Runtime Config Store
  - Authoritative source of live overrides
- Audit Log
  - Immutable records for every change and rollback

### 4.2 Orchestrator Runtime Plane

- Sensing Layer
  - Collects queue depth, stage progression, per-policy throughput, error rates, latency, resource pressure
- Decision Layer
  - Rule-based controller first, optional contextual bandit later (feature-flagged)
- Actuation Layer
  - Applies allowed hot settings via control plane
- Verification Layer
  - Confirms propagation and impact against expected bounds

### 4.3 Safety and Governance Plane

- Guardrails
  - Cooldown windows
  - Per-window change budgets
  - Denylist for unsafe keys
- Rollback Controller
  - Triggered by hard SLO breaches or operator command

## 5. Control Loop

1. Sense
   - Read current pipeline and service telemetry snapshot
2. Evaluate
   - Compare against SLO targets and policy thresholds
3. Decide
   - Choose bounded action set and expected impact
4. Apply
   - Submit config patch through runtime config API
5. Verify
   - Confirm applied version and monitor short-window outcomes
6. Learn
   - Record action effectiveness for future policy scoring

## 6. Action Tiers

Tier 1 (first enablement):
- orchestrator.polling_interval_seconds
- orchestrator.max_concurrent_tasks
- orchestrator.resource_limits.*

Tier 2:
- mcp_bus timeout/retry/circuit thresholds

Tier 3:
- fact_checker query fanout/evidence/deep-crawl timeout knobs

## 7. Safety Gates and Rollback

Pre-apply gates:
- Key allowed and hot-reloadable
- Value within schema bounds
- Change budget not exhausted
- Cooldown satisfied

Post-apply gates:
- Apply acknowledgement received
- Version propagated within timeout
- No hard SLO breach in validation window

Rollback triggers:
- Error rate spike above threshold for two consecutive windows
- Throughput collapse with rising queue depth
- Resource saturation sustained beyond guardrails

## 8. Canonical Interfaces

- Status endpoints must expose:
  - applied_config_version
  - last_apply_status
  - last_decision
  - autonomic_mode (disabled, shadow, active)

- Decision record must include:
  - timestamp
  - sensed state summary
  - chosen action(s)
  - safety checks passed/failed
  - expected and observed impact

## 9. Deployment Modes

- Disabled: no autonomic behavior
- Shadow: decisions computed and logged, no live actions
- Active: bounded live actions enabled

## 10. Known Drift to Resolve Before Active Mode

- Standardize workflow_orchestrator port references to 8023
- Ensure policy naming consistency for analysis_to_fact_check references
- Correct override-expiry reliability path in policy helper logic

## 11. Traceability

Primary execution plan:
- docs/architecture/AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md

Execution checklist:
- docs/architecture/AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md

Operations guide:
- docs/operations/AUTONOMIC_ORCHESTRATOR_RUNBOOK.md

Control-plane dependency:
- docs/architecture/LIVE_TUNING_CONTROL_PLANE_DESIGN.md
