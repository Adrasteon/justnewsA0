# Multi-Source Refactor — M2 Sign-Off Evidence Index

**Date:** 2026-02-22  
**Scope:** Central index for M2 gate evidence (QA + Ops + Product review)  
**Status:** Approved for current purposes (2026-02-22); follow-up artifacts tracked below

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
| Provenance field completeness | Sample records with required publication fields | [Provenance Sample Evidence (Local, 2026-02-22)](./MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_2026-02-22_LOCAL.md) + [Parity Provenance Report (Dev, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_provenance_dev_20260316T123606Z.md) + [Parity Provenance Report (Staging-tagged, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_provenance_staging_20260316T123625Z.md) + [Provenance Sample Evidence Template (2026-02-22)](./MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_TEMPLATE_2026-02-22.md) | Data/Eng | In progress | Dev and staging-tagged captures show `10/10` complete; re-run against true staging environment for final closure |
| Dashboard + alert readiness | Panel URLs + alert rule IDs | Dashboard: `docs/grafana/multi-source-refactor-observability-dashboard.json` (UID `justnews-multi-source-refactor`, panels `101,102,103,104,105`); Alerts: `monitoring/alerts/multi_source_refactor_alerts.yml` (`MultiSourceVerifiedShareLow`, `MultiSourcePromotionFailuresSpike`) | Ops | In progress | Definition-level links attached; deploy/import URLs and environment screenshots still required for final closure |
| M2 sign-off summary | Review note with approvers and decision | [M2 Sign-Off Summary (Draft, 2026-02-22)](./MULTI_SOURCE_REFACTOR_M2_SIGNOFF_SUMMARY_2026-02-22_DRAFT.md) | Product/Ops | Complete (current purposes) | Decision recorded as `go (current purposes)`; parity artifacts remain as follow-up |

## 4) Minimum Artifact Bundle Checklist

- [x] Latest focused test results attached
- [x] CI workflow run URL attached
- [x] Rollback drill payloads attached (local harness)
- [x] Metrics snapshot attached (local harness)
- [x] Provenance sample snapshot attached (local harness)
- [x] Dashboard/alert links attached
- [x] Approver sign-off note attached (draft)

## 5) Last Updated

- 2026-02-22: Initial evidence index created.
- 2026-02-22: Seeded with commit-linked evidence and fresh focused test result (`24 passed`).
- 2026-03-16: Refreshed automated parity capture links (dev + staging-tagged) with live `/metrics` status `200` on local orchestrator.

## 6) Remaining External Artifacts

The following items require non-local artifacts to complete M2 sign-off:

1. **CI run URL (required)**
  - Workflow: `workflow-orchestrator-control-plane-tests`
  - Required fields: run URL, commit SHA, branch, run status, timestamp.

2. **Dashboard + alert links (required)**
  - Required fields: dashboard URL(s), panel ID(s), alert rule ID(s), environment, screenshot(s) or export references.
  - Minimum scope: `published_verified_share` and promotion failure reason signals.

3. **Approver sign-off note (completed for current purposes)**
  - Required fields: approver names/roles (QA, Ops, Product), decision (`go`/`no-go`), timestamp, conditions/follow-ups.

4. **Dev/staging parity artifacts (recommended for closure quality)**
  - Dev/staging `/metrics` snapshot link.
  - Dev/staging rollback drill artifact link.
  - Dev/staging provenance sample export link.
  - Optional automation helper: `scripts/ops/capture_refactor_parity_artifacts.py`.
  - Provenance helper: `scripts/ops/export_refactor_provenance_sample.py`.
  - Execute collection using [Dev/Staging Parity Runsheet (2026-02-22)](./MULTI_SOURCE_REFACTOR_DEV_STAGING_PARITY_RUNSHEET_2026-02-22.md).

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
- Execution runsheet: [Dev/Staging Parity Runsheet (2026-02-22)](./MULTI_SOURCE_REFACTOR_DEV_STAGING_PARITY_RUNSHEET_2026-02-22.md)

### 7.3 M2 Approver Sign-Off

- Draft summary document: [M2 Sign-Off Summary (Draft, 2026-02-22)](./MULTI_SOURCE_REFACTOR_M2_SIGNOFF_SUMMARY_2026-02-22_DRAFT.md)

- QA approver (name/role): `Approved for current purposes (project directive)`
- Ops approver (name/role): `Approved for current purposes (project directive)`
- Product approver (name/role): `Approved for current purposes (project directive)`
- Decision: `go (current purposes)`
- Timestamp (UTC): `2026-02-22`
- Conditions/follow-ups: `Complete dev/staging parity artifacts as post-approval follow-up.`

### 7.4 Automated Parity Capture (Dry Run)

- Environment: `dev`
- Orchestrator URL: `http://localhost:8023`
- Capture helper: `scripts/ops/capture_refactor_parity_artifacts.py`
- JSON artifact: [Parity Capture JSON (Dev, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_dev_20260316T123130Z.json)
- Markdown artifact: [Parity Capture Report (Dev, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_dev_20260316T123130Z.md)
- Notes: `/runtime-config` snapshots succeeded; `/metrics` returned `200` on this endpoint. This remains local-orchestrator evidence, not true external staging parity.

### 7.5 Automated Parity Capture (Staging-Tagged Run)

- Environment: `staging`
- Orchestrator URL: `http://localhost:8023` (fallback from `ORCH_URL`; `STAGING_ORCH_URL` not set)
- Capture helper: `scripts/ops/capture_refactor_parity_artifacts.py`
- JSON artifact: [Parity Capture JSON (Staging, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_staging_20260316T123152Z.json)
- Markdown artifact: [Parity Capture Report (Staging, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_staging_20260316T123152Z.md)
- Dashboard metadata: `docs/grafana/multi-source-refactor-observability-dashboard.json`
- Panel IDs: `101, 102, 103, 104, 105`
- Alert IDs: `MultiSourceVerifiedShareLow`, `MultiSourcePromotionFailuresSpike`
- Notes: `/runtime-config` snapshots succeeded; `/metrics` returned `200` on this endpoint. Re-run against true staging endpoint once `STAGING_ORCH_URL` is available to close environment-level staging parity.

### 7.6 Automated Provenance Capture

- Capture helper: `scripts/ops/export_refactor_provenance_sample.py`
- Required fields validated: `publication_lane`, `source_count`, `unique_domain_count`, `confidence_tier`, `provenance_trace_id`, `decision_reason_codes`, `policy_version`, `policy_enabled`, `policy_thresholds`

Dev capture:
- Environment: `dev`
- JSON artifact: [Parity Provenance JSON (Dev, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_provenance_dev_20260316T123606Z.json)
- Markdown artifact: [Parity Provenance Report (Dev, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_provenance_dev_20260316T123606Z.md)
- Result summary: `sample_size=10`, `complete_valid=10`, `incomplete_invalid=0`

Staging-tagged capture:
- Environment: `staging`
- JSON artifact: [Parity Provenance JSON (Staging-tagged, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_provenance_staging_20260316T123625Z.json)
- Markdown artifact: [Parity Provenance Report (Staging-tagged, 2026-03-16)](../../logs/operations/refactor_parity/multi_source_refactor_provenance_staging_20260316T123625Z.md)
- Result summary: `sample_size=10`, `complete_valid=10`, `incomplete_invalid=0`
- Notes: Captures are produced from local runtime data with environment tags. Re-run on true staging data plane for final environment-level parity closure.
