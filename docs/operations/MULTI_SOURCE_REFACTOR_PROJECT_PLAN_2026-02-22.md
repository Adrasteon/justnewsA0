# Multi-Source Integrity Refactor — Project Plan

**Date:** 2026-02-22  
**Program:** JustNews Living Stories  
**Status:** In progress — M1/M2 implementation active; control-plane CI gate added (2026-02-22)  
**Related Docs:**
- [Investor One-Pager: Multi-Source Integrity Refactor (2026-02-22)](./INVESTOR_ONE_PAGER_MULTI_SOURCE_REFACTOR_2026-02-22.md)
- [Investor Technical Appendix: Multi-Source Integrity Refactor (2026-02-22)](./INVESTOR_TECH_APPENDIX_MULTI_SOURCE_REFACTOR_2026-02-22.md)

## 1) Objective

Implement a production-safe refactor that increases multi-source verification quality while preserving publication timeliness via a dual-lane model:

- **Lane A:** `verified_story` (multi-source corroborated)
- **Lane B:** `developing_brief` (singleton/low-diversity with explicit caveat)

## 2) Success Criteria (Definition of Done)

The refactor is considered complete when all conditions are true for a sustained validation window (minimum 7 days in target environment):

1. Lane metadata is present on 100% of new publications.
2. Metrics and dashboards for lane mix and source diversity are live and correct.
3. Runtime policy controls support per-environment toggle + versioned rollback.
4. Acceptance tests pass for lane routing, provenance fields, and fallback behavior.
5. On-call runbook and action checklist are completed and evidenced.

## 3) Scope

### In Scope (MVP)

- Lane assignment and publication metadata.
- Lane-aware policy routing and thresholds.
- Required telemetry + dashboards.
- Governance controls (audit reason codes, config versioning, rollback).
- Controlled phased rollout.

### Out of Scope (MVP)

- Major UI redesign.
- Rewriting unrelated agents.
- Non-critical schema redesign beyond fields required for lane/provenance support.

## 4) Workstreams

### WS1 — Policy & Orchestrator Controls

- Add lane-aware routing logic.
- Separate Lane A eligibility from Lane B fallback eligibility.
- Add environment-tunable thresholds and feature flags.

### WS2 — Data Contract & Provenance

- Add/validate publication metadata fields:
  - `publication_lane`
  - `source_count`
  - `unique_domain_count`
  - `confidence_tier`
  - `provenance_trace_id`
- Persist lane decision reason codes and policy version.

### WS3 — Observability

- Emit required metrics:
  - `published_total{lane}`
  - `published_verified_share`
  - `median_unique_domains_per_story`
  - `cluster_promotion_failures{reason}`
  - `singleton_to_verified_conversion_total`
- Build/validate dashboards and alerts.

### WS4 — QA, Rollout, and Ops Readiness

- Execute integration/regression tests.
- Perform staged rollout (dev → canary → full).
- Validate rollback drill and incident handling.

## 5) Milestones and Timeline (Industry-Norm Sequencing)

> Dates assume kickoff on 2026-02-23.

### M0 — Kickoff and Baseline (2026-02-23 to 2026-02-24)

- Confirm baseline metrics and current lane composition.
- Freeze MVP scope and acceptance criteria.
- Assign owners and on-call coverage.

### M1 — Instrumentation First (2026-02-25 to 2026-02-28)

- Implement lane metadata fields and reason codes.
- Publish initial lane telemetry and dashboard panels.
- Validate data correctness in dev.

**Exit Gate:** 100% new records contain lane + provenance metadata in dev.

### M2 — Policy Routing Implementation (2026-03-01 to 2026-03-05)

- Implement lane-aware thresholds and fallback logic.
- Add runtime config toggles and versioned rollback hooks.
- Run test suite and failure mode drills.

**Exit Gate:** Test pass + verified rollback path in dev.

### M3 — Canary Rollout (2026-03-06 to 2026-03-08)

- Enable for canary environment/traffic slice.
- Monitor verified-share, latency, and contradiction indicators.
- Tune thresholds with documented reason codes.

**Exit Gate:** No Sev1/Sev2 quality regressions; KPI trend acceptable.

### M4 — Full Rollout and Stabilization (2026-03-09 to 2026-03-13)

- Expand to full target environment.
- Confirm sustained KPI behavior.
- Publish closeout report and handoff to steady-state ops.

**Exit Gate:** DoD satisfied for 7-day validation window.

## 6) RACI

| Deliverable | Eng Lead | Data/ML | SRE/Ops | Product | QA |
| --- | --- | --- | --- | --- | --- |
| Lane policy implementation | A/R | C | C | C | C |
| Provenance data contract | A/R | R | C | C | C |
| Dashboards/alerts | C | R | A/R | C | C |
| Rollout + rollback drills | C | C | A/R | C | R |
| Acceptance sign-off | C | C | R | A | A/R |

Legend: **A** = Accountable, **R** = Responsible, **C** = Consulted

## 7) Dependencies

- Runtime config service supports versioned apply/rollback.
- Metrics pipeline and dashboards available in target environment.
- Reliable source/domain normalization for diversity counts.
- Staging or canary environment with representative data volume.

## 8) Risk Register (Top 5)

1. **Throughput regression** when tightening Lane A thresholds.  
   - Mitigation: Lane B fallback + phased threshold increase.
2. **Sparse-topic undercoverage**.  
   - Mitigation: topic-aware threshold profiles; explicit “developing” status.
3. **Metric drift/misclassification**.  
   - Mitigation: telemetry validation checks and sample audits each phase.
4. **Operational complexity**.  
   - Mitigation: strict change windows + reason-tagged config changes.
5. **Rollback latency** under incident conditions.  
   - Mitigation: pre-validated rollback drill before canary.

## 9) Acceptance Test Matrix (Minimum)

- **AT-01 Lane Routing:** qualifying multi-source candidates route to `verified_story`.
- **AT-02 Fallback:** non-qualifying candidates route to `developing_brief` with caveat fields.
- **AT-03 Metadata Completeness:** required lane/provenance fields present and non-null.
- **AT-04 Metrics Integrity:** lane counters and diversity metrics reconcile with sampled records.
- **AT-05 Rollback:** config rollback reverts behavior within defined SLA.

## 10) Go/No-Go Gates

### Gate A (Pre-Canary)

- All AT tests pass in dev.
- Dashboard signals stable for 24h.
- Rollback drill successful.

### Gate B (Pre-Full Rollout)

- Canary shows acceptable quality/latency trend.
- No unresolved Sev1/Sev2 incidents.
- Product + Ops sign-off recorded.

## 11) Communication Cadence

- Daily standup update during M1–M4.
- End-of-milestone review notes (decision log + KPI snapshot).
- Incident channel protocol during canary/full rollout windows.

## 12) Deliverables Checklist

- [ ] Lane routing merged and tested
- [ ] Provenance contract deployed
- [ ] Dashboards and alerts live
- [ ] Rollback drill evidence attached
- [ ] Runbook + action checklist completed
- [ ] Final closeout summary published
