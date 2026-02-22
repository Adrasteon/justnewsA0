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
| Metrics contract tests | `/metrics` contract test evidence | [Metrics Snapshot (Local, 2026-02-22)](./MULTI_SOURCE_REFACTOR_METRICS_SNAPSHOT_2026-02-22_LOCAL.md) + commits: `49302b1`, `1610257` | QA | In progress | Local snapshot attached; add dev/staging snapshot for M2 closure |
| CI gate proof | Workflow run for `workflow-orchestrator-control-plane-tests` | https://github.com/Adrasteon/justnewsA0/actions/runs/22280864776 (`success`) | Eng | In progress | Branch `feat/integrity-refactor`, run #3, head SHA `89bb1e86b543635062e389f8b16aa9bc542df79f` |
| Rollback drill proof | Apply/rollback JSON + before/after `owner_overrides` | [Rollback Drill Artifact (Local, 2026-02-22)](./MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_2026-02-22_LOCAL.md) + [Rollback Drill Artifact Template (2026-02-22)](./MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_TEMPLATE_2026-02-22.md) + commit `89bb1e8` | Ops | In progress | Local harness artifact attached; add real dev run artifact for M2 closure |
| Lane behavior reversion | Sample lane decision before/apply/rollback | [Rollback Drill Artifact (Local, 2026-02-22)](./MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_2026-02-22_LOCAL.md) + commit `89bb1e8` (`test_runtime_rollback_sla_and_lane_revert`) | QA/Ops | In progress | Includes observed `developing_brief -> verified_story -> developing_brief` |
| Provenance field completeness | Sample records with required publication fields | [Provenance Sample Evidence (Local, 2026-02-22)](./MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_2026-02-22_LOCAL.md) + [Provenance Sample Evidence Template (2026-02-22)](./MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_TEMPLATE_2026-02-22.md) | Data/Eng | In progress | Local sample pass attached; add dev/staging export for M2 closure |
| Dashboard + alert readiness | Panel URLs + alert rule IDs | Dashboard: `docs/grafana/multi-source-refactor-observability-dashboard.json` (UID `justnews-multi-source-refactor`, panels `101,102,103,104,105`); Alerts: `monitoring/alerts/multi_source_refactor_alerts.yml` (`MultiSourceVerifiedShareLow`, `MultiSourcePromotionFailuresSpike`) | Ops | In progress | Definition-level links attached; deploy/import URLs and environment screenshots still required for final closure |
| M2 sign-off summary | Review note with approvers and decision | `<add link>` | Product/Ops | Pending | Final go/no-go for M2 closure |

## 4) Minimum Artifact Bundle Checklist

- [x] Latest focused test results attached
- [x] CI workflow run URL attached
- [x] Rollback drill payloads attached (local harness)
- [x] Metrics snapshot attached (local harness)
- [x] Provenance sample snapshot attached (local harness)
- [x] Dashboard/alert links attached
- [ ] Approver sign-off note attached

## 5) Last Updated

- 2026-02-22: Initial evidence index created.
- 2026-02-22: Seeded with commit-linked evidence and fresh focused test result (`24 passed`).

## 6) Remaining External Artifacts

The following items require non-local artifacts to complete M2 sign-off:

1. **CI run URL (required)**
  - Workflow: `workflow-orchestrator-control-plane-tests`
  - Required fields: run URL, commit SHA, branch, run status, timestamp.

2. **Dashboard + alert links (required)**
  - Required fields: dashboard URL(s), panel ID(s), alert rule ID(s), environment, screenshot(s) or export references.
  - Minimum scope: `published_verified_share` and promotion failure reason signals.

3. **Approver sign-off note (required)**
  - Required fields: approver names/roles (QA, Ops, Product), decision (`go`/`no-go`), timestamp, conditions/follow-ups.

4. **Dev/staging parity artifacts (recommended for closure quality)**
  - Dev/staging `/metrics` snapshot link.
  - Dev/staging rollback drill artifact link.
  - Dev/staging provenance sample export link.

## 7) Fill-In Blocks (External Artifacts)

### 7.1 CI Workflow Run Evidence

- Workflow: `workflow-orchestrator-control-plane-tests`
- Run URL: `https://github.com/Adrasteon/justnewsA0/actions/runs/22280864776`
- Commit SHA: `89bb1e86b543635062e389f8b16aa9bc542df79f`
- Branch: `feat/integrity-refactor`
- Run status: `success`
- Timestamp (UTC): `2026-02-22T16:25:59Z` (updated `2026-02-22T16:31:15Z`)

### 7.2 Dashboard and Alert Evidence

- Environment: `repo definition (pending dev/staging import)`
- Dashboard URL(s): `docs/grafana/multi-source-refactor-observability-dashboard.json`
- Panel ID(s): `101, 102, 103, 104, 105`
- Alert rule ID(s): `MultiSourceVerifiedShareLow`, `MultiSourcePromotionFailuresSpike`
- Screenshot/export link(s): `<pending after dashboard import>`
- Notes: `Alert definitions stored at monitoring/alerts/multi_source_refactor_alerts.yml`

### 7.3 M2 Approver Sign-Off

- QA approver (name/role): `<paste>`
- Ops approver (name/role): `<paste>`
- Product approver (name/role): `<paste>`
- Decision: `<go|no-go|conditional>`
- Timestamp (UTC): `<paste timestamp>`
- Conditions/follow-ups: `<paste notes>`
