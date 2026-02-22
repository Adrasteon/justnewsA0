# AI Assistant Refactor Guardrails

**Date:** 2026-02-22  
**Scope:** Multi-Source Integrity Refactor execution support  
**Audience:** Engineers, operators, and AI-assisted implementers

## 1) Purpose

Define operating guardrails for AI-assisted implementation so refactor work is:

- aligned to approved scope,
- safe to roll out,
- auditable,
- and reversible.

## 2) Source of Truth (Priority Order)

1. [MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md](./MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md)
2. [MULTI_SOURCE_REFACTOR_ACTION_CHECKLIST_2026-02-22.md](./MULTI_SOURCE_REFACTOR_ACTION_CHECKLIST_2026-02-22.md)
3. [INVESTOR_TECH_APPENDIX_MULTI_SOURCE_REFACTOR_2026-02-22.md](./INVESTOR_TECH_APPENDIX_MULTI_SOURCE_REFACTOR_2026-02-22.md)
4. [INVESTOR_ONE_PAGER_MULTI_SOURCE_REFACTOR_2026-02-22.md](./INVESTOR_ONE_PAGER_MULTI_SOURCE_REFACTOR_2026-02-22.md)

When guidance conflicts, follow this order and log the decision.

## 3) Allowed vs. Not Allowed

### Allowed

- Implement lane-aware routing and metadata required by approved plan.
- Add/adjust telemetry and alerts defined in project docs.
- Make minimal, focused changes needed to satisfy acceptance criteria.
- Add rollback hooks and validation checks where missing.

### Not Allowed (Without Explicit Approval)

- Broad redesigns outside refactor scope.
- Unrelated schema or agent rewrites.
- Silent behavior changes without audit/reason logging.
- Threshold tightening directly in production without staged rollout.

## 4) Non-Negotiable Safety Rules

1. **No production-only first deploys.** Changes must flow dev → canary → full.
2. **Feature-flag first.** New routing behavior must be toggled and reversible.
3. **Rollback-ready before rollout.** Validate rollback in non-prod before canary.
4. **Evidence required.** Each milestone must produce test and metric artifacts.
5. **No hidden scope expansion.** Any out-of-scope requirement must be explicitly documented and approved.

## 5) Required Implementation Outputs per Change Set

For each AI-assisted PR/change set:

- Problem statement and intended outcome.
- Exact files changed and rationale.
- Test evidence (unit/integration/regression where relevant).
- Metrics impact and dashboard references.
- Rollback procedure and expected revert signals.

## 6) Acceptance Gate Checklist (AI Must Satisfy)

- [ ] Scope aligns with approved project plan.
- [ ] Lane metadata/provenance behavior preserved or improved.
- [ ] Required telemetry emitted and validated.
- [ ] Rollback path documented and tested.
- [ ] No unresolved Sev1/Sev2 regressions.
- [ ] Change log entry with reason code and operator-readable summary.

## 7) Prompt Template for AI Implementers

Use this template when assigning implementation tasks:

1. **Objective:** one sentence tied to project plan milestone.
2. **In-scope changes:** list exact components/files allowed.
3. **Out-of-scope constraints:** list forbidden changes.
4. **Acceptance tests:** required checks and success criteria.
5. **Rollout constraints:** environment order and rollback expectation.
6. **Deliverables:** files updated + evidence summary format.

## 8) Example Assignment (Short Form)

- Objective: Implement lane metadata persistence for publication output.
- In scope: orchestrator routing and publication payload fields only.
- Out of scope: UI redesign, unrelated model tuning.
- Tests: metadata completeness + integration pass.
- Rollout: dev only in this task.
- Deliverable: patch + evidence notes + rollback confirmation.

## 9) Escalation Rules

Escalate to human owner before proceeding when:

- policy conflicts are detected,
- acceptance criteria are ambiguous,
- rollback behavior is uncertain,
- or observed metrics suggest trust-quality regression.

## 10) Definition of Done (AI Task Level)

An AI task is done only when code/docs changes are merged-ready, acceptance checks pass, rollback is clear, and evidence is attached in the corresponding implementation ticket.
