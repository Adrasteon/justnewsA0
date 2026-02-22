# Multi-Source Refactor — M2 Sign-Off Evidence Index

**Date:** 2026-02-22  
**Scope:** Central index for M2 gate evidence (QA + Ops + Product review)  
**Status:** Active (in-progress)

## 1) Purpose

Provide one canonical location for all artifacts required to close M2 exit criteria in the project plan.

## 2) M2 Exit Gate Mapping

- **Exit Gate:** “Test pass + verified rollback path in dev.”
- **Primary references:**
  - [Multi-Source Refactor Project Plan (2026-02-22)](./MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md)
  - [Multi-Source Refactor Action Checklist (2026-02-22)](./MULTI_SOURCE_REFACTOR_ACTION_CHECKLIST_2026-02-22.md)
  - [Multi-Source Refactor Runtime Tuning Runbook (2026-02-22)](./MULTI_SOURCE_REFACTOR_RUNTIME_TUNING_RUNBOOK_2026-02-22.md)
  - [Multi-Source Refactor Metrics Note (2026-02-22)](./MULTI_SOURCE_REFACTOR_METRICS_NOTE_2026-02-22.md)

## 3) Evidence Table

| Evidence Category | Required Artifact | Link | Owner | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| Runtime control-plane tests | Focused test run output for endpoint + override + lane suite | `<add link>` | QA | Pending | Expected suite includes control-plane endpoint tests and lane metadata tests |
| Metrics contract tests | `/metrics` contract test evidence | `<add link>` | QA | Pending | Must include required lane metric series presence |
| CI gate proof | Workflow run for `workflow-orchestrator-control-plane-tests` | `<add link>` | Eng | Pending | Include run URL + commit SHA |
| Rollback drill proof | Apply/rollback JSON + before/after `owner_overrides` | `<add link>` | Ops | Pending | Must show removal of stale lane overrides |
| Lane behavior reversion | Sample lane decision before/apply/rollback | `<add link>` | QA/Ops | Pending | Show `developing_brief -> verified_story -> developing_brief` where applicable |
| Provenance field completeness | Sample records with required publication fields | `<add link>` | Data/Eng | Pending | Verify `publication_lane`, counts, confidence, trace, reason/version fields |
| Dashboard + alert readiness | Panel URLs + alert rule IDs | `<add link>` | Ops | Pending | Verified share + promotion failure alerts |
| M2 sign-off summary | Review note with approvers and decision | `<add link>` | Product/Ops | Pending | Final go/no-go for M2 closure |

## 4) Minimum Artifact Bundle Checklist

- [ ] Latest focused test results attached
- [ ] CI workflow run URL attached
- [ ] Rollback drill payloads attached
- [ ] Metrics snapshot attached
- [ ] Provenance sample snapshot attached
- [ ] Dashboard/alert links attached
- [ ] Approver sign-off note attached

## 5) Last Updated

- 2026-02-22: Initial evidence index created.
