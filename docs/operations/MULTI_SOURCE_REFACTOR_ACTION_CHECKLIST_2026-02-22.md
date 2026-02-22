# Multi-Source Integrity Refactor — Action Checklist

**Date:** 2026-02-22  
**Use:** Execution checklist for engineering + operations  
**Companion Plan:** [MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md](./MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md)

## 0) Ownership and Change Window

- [ ] Assign **Implementation Owner**
- [ ] Assign **Ops On-Call Owner**
- [ ] Assign **QA Owner**
- [ ] Define change window(s)
- [ ] Create ticket and paste this checklist

## 1) Preflight Baseline (Before Any Code Change)

- [ ] Capture baseline lane mix (singleton vs multi-source)
- [ ] Capture baseline source-diversity distribution
- [ ] Capture baseline publication latency metrics
- [ ] Capture baseline contradiction/consistency indicators
- [ ] Confirm rollback path for runtime config is functional

**Evidence to attach**
- [ ] Baseline dashboard screenshots/queries
- [ ] Current config snapshot

## 2) Data Contract and Schema/Storage Readiness

- [ ] Ensure publication record supports/contains:
  - [ ] `publication_lane`
  - [ ] `source_count`
  - [ ] `unique_domain_count`
  - [ ] `confidence_tier`
  - [ ] `provenance_trace_id`
- [ ] Add lane decision reason code field (or equivalent audit field)
- [ ] Add policy version/timestamp persistence at decision time
- [ ] Validate backward compatibility for existing readers

**Acceptance checks**
- [ ] Metadata completeness check passes on sample set
- [ ] No breaking changes for existing consumers

## 3) Policy and Routing Implementation

Reference: [MULTI_SOURCE_REFACTOR_RUNTIME_TUNING_RUNBOOK_2026-02-22.md](./MULTI_SOURCE_REFACTOR_RUNTIME_TUNING_RUNBOOK_2026-02-22.md)

- [ ] Implement lane-aware routing:
  - [ ] Lane A eligibility (`verified_story`)
  - [ ] Lane B fallback (`developing_brief`)
- [ ] Add environment-tunable threshold controls
- [ ] Add feature flag(s) for staged enablement
- [ ] Add topic-aware threshold override capability (if configured)
- [ ] Ensure explicit caveat labeling for Lane B output

**Acceptance checks**
- [ ] AT-01 Lane Routing pass
- [ ] AT-02 Fallback pass

## 4) Telemetry, Dashboard, and Alerting

Reference: [MULTI_SOURCE_REFACTOR_METRICS_NOTE_2026-02-22.md](./MULTI_SOURCE_REFACTOR_METRICS_NOTE_2026-02-22.md)

- [ ] Emit required metrics:
  - [ ] `published_total{lane}`
  - [ ] `published_verified_share`
  - [ ] `median_unique_domains_per_story`
  - [ ] `cluster_promotion_failures{reason}`
  - [ ] `singleton_to_verified_conversion_total`
- [ ] Build/update dashboard panels for lane mix and promotion funnel
- [ ] Add alert for verified-share regression
- [ ] Add alert for spike in promotion failures by reason

**Acceptance checks**
- [ ] Metrics reconcile against sampled records
- [ ] Alert tests pass (synthetic or controlled trigger)

## 5) Test and Validation

- [ ] Unit tests for lane assignment logic
- [ ] Integration tests for orchestrator policy path
- [ ] Regression tests for unaffected publishing flow
- [ ] Data quality tests for domain/source counting
- [ ] Rollback test in non-prod

**Exit criteria**
- [ ] AT-03 Metadata Completeness pass
- [ ] AT-04 Metrics Integrity pass
- [ ] AT-05 Rollback pass

## 6) Rollout Procedure

### Dev
- [ ] Enable feature flags in dev
- [ ] Run burn-in for at least 24h
- [ ] Review KPI movement and error budget

### Canary
- [ ] Enable canary slice
- [ ] Monitor for 24–48h
- [ ] Review incident log and quality trends

### Full
- [ ] Approvals from Product + Ops + QA
- [ ] Enable full rollout
- [ ] Intensified monitoring window (first 24h)

## 7) Go/No-Go Checklist

### Pre-Canary
- [ ] All required tests pass in dev
- [ ] Dashboards/alerts validated
- [ ] Rollback drill evidence attached
- [ ] No open Sev1/Sev2 blockers

### Pre-Full
- [ ] Canary KPIs within approved ranges
- [ ] No unresolved critical incidents
- [ ] Sign-off captured from owners

## 8) Rollback Checklist

- [ ] Trigger runtime-config rollback to last known good version
- [ ] Verify behavior reverted (lane mix + policy decision output)
- [ ] Verify removed lane-policy overrides are fully cleared (no stale topic override influence)
- [ ] Confirm alert noise normalizes
- [ ] Publish incident summary and next-step decision

## 9) Completion and Handoff

- [ ] Publish implementation summary (what changed, why, measured impact)
- [ ] Link final KPI snapshot
- [ ] Link post-rollout incident review (if any)
- [ ] Mark ticket complete with evidence bundle

## 10) Evidence Index Template

| Item | Link/Artifact | Owner | Status |
| --- | --- | --- | --- |
| Baseline metrics snapshot | `<link>` | `<owner>` | Pending |
| Config snapshot (pre-change) | `<link>` | `<owner>` | Pending |
| Test results bundle | `<link>` | `<owner>` | Pending |
| Canary KPI report | `<link>` | `<owner>` | Pending |
| Rollback drill proof | `<link>` | `<owner>` | Pending |
| Final closeout summary | `<link>` | `<owner>` | Pending |
