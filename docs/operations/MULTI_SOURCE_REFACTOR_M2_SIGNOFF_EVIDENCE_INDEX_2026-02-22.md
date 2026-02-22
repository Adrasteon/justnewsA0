# Multi-Source Refactor — M2 Sign-Off Evidence Index

**Date:** 2026-02-22  
**Scope:** Central index for M2 gate evidence (QA + Ops + Product review)  
**Status:** Active (in-progress; seeded with implementation evidence)

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
| Runtime control-plane tests | Focused test run output for endpoint + override + lane suite | Local run: `24 passed in 8.70s` (2026-02-22) | QA | In progress | Command: `pytest -q tests/unit/test_workflow_orchestrator_runtime_control_plane_endpoints.py tests/unit/test_workflow_orchestrator_runtime_examples.py tests/unit/test_workflow_orchestrator_runtime_examples_endpoint.py tests/unit/test_workflow_orchestrator_runtime_overrides.py tests/unit/test_workflow_orchestrator_lane_metadata.py` |
| Metrics contract tests | `/metrics` contract test evidence | Commits: `49302b1`, `1610257` | QA | In progress | Includes `test_metrics_endpoint_exposes_lane_observability_contract` |
| CI gate proof | Workflow run for `workflow-orchestrator-control-plane-tests` | `.github/workflows/workflow-orchestrator-control-plane-tests.yml` (commit `235e60e`) | Eng | In progress | Attach Actions run URL from PR/push execution |
| Rollback drill proof | Apply/rollback JSON + before/after `owner_overrides` | [Rollback Drill Artifact Template (2026-02-22)](./MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_TEMPLATE_2026-02-22.md) + commit `89bb1e8` | Ops | In progress | Fill template with environment run outputs and link completed artifact |
| Lane behavior reversion | Sample lane decision before/apply/rollback | Commit `89bb1e8` (`test_runtime_rollback_sla_and_lane_revert`) | QA/Ops | In progress | Exercises `developing_brief -> verified_story -> developing_brief` path |
| Provenance field completeness | Sample records with required publication fields | [Provenance Sample Evidence Template (2026-02-22)](./MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_TEMPLATE_2026-02-22.md) | Data/Eng | Pending | Fill with sampled records validating lane/provenance completeness |
| Dashboard + alert readiness | Panel URLs + alert rule IDs | `<add link>` | Ops | Pending | Verified share + promotion failure alerts |
| M2 sign-off summary | Review note with approvers and decision | `<add link>` | Product/Ops | Pending | Final go/no-go for M2 closure |

## 4) Minimum Artifact Bundle Checklist

- [x] Latest focused test results attached
- [ ] CI workflow run URL attached
- [ ] Rollback drill payloads attached
- [ ] Metrics snapshot attached
- [ ] Provenance sample snapshot attached
- [ ] Dashboard/alert links attached
- [ ] Approver sign-off note attached

## 5) Last Updated

- 2026-02-22: Initial evidence index created.
- 2026-02-22: Seeded with commit-linked evidence and fresh focused test result (`24 passed`).
