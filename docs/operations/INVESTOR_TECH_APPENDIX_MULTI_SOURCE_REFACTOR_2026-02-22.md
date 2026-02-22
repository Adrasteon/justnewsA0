# Investor Technical Appendix: Multi-Source Integrity Refactor

**Date:** 2026-02-22  
**Program:** JustNews Living Stories  
**Companion Doc:** `INVESTOR_ONE_PAGER_MULTI_SOURCE_REFACTOR_2026-02-22.md`

## 1) Problem Framing

The current production posture allows high publication volume, but quality composition is skewed toward singleton outputs. At the same time, parts of the discovery pipeline rely on source-diversity thresholds that can stall backlog conversion when domain variety is constrained. This creates inconsistent policy pressure across pipeline stages.

## 2) Refactor Objectives

- Align runtime behavior with multi-source-first product positioning.
- Preserve timeliness while increasing evidence quality.
- Make quality posture observable and auditable at every stage.

## 3) Architecture Adjustment (MVP)

### 3.1 Dual-Lane Output Contract

- **Lane A (Verified Story):** multi-source corroborated output.
- **Lane B (Developing Brief):** singleton or low-diversity output with explicit caveats.

Each published item carries:

- `publication_lane` (`verified_story` | `developing_brief`)
- `source_count`
- `unique_domain_count`
- `confidence_tier`
- `provenance_trace_id`

### 3.2 Policy Layer Changes

- Introduce lane-aware threshold policy in orchestrator controls.
- Apply strict source-diversity gates only to Lane A eligibility.
- Keep Lane B available for freshness-sensitive topics.
- Add environment-tunable config keys for gradual tightening.

### 3.3 Discovery/Clustering Behavior

- Preserve clustering logic but add diagnostics for near-miss clusters (e.g., candidate sets failing only source-diversity).
- Track reasons for cluster non-promotion to guide policy tuning.
- Maintain backlog hygiene with explicit counters for “eligible”, “ineligible”, and “deferred”.

## 4) Data and Telemetry Additions

## 4.1 Required Metrics

- `published_total{lane}`
- `published_verified_share`
- `median_unique_domains_per_story`
- `cluster_promotion_failures{reason}`
- `singleton_to_verified_conversion_total`

## 4.2 Operational Dashboards

- Lane mix over time.
- Backlog and cluster promotion funnel.
- Source-diversity distribution by topic.
- Contradiction/consistency issue rates by lane.

## 4.3 Auditability

- Persist provenance fields for each output.
- Persist lane decision reason codes.
- Retain policy version/timestamp used at publication time.

## 5) Rollout Plan

### Phase 1: Instrument and Label

- Add lane metadata and quality counters.
- Keep existing publish behavior but classify all output into lanes.
- Validate telemetry correctness and dashboard coverage.

### Phase 2: Enforce Lane Semantics

- Require minimum multi-source gates for Lane A classification.
- Route non-qualifying candidates to Lane B with explicit status labels.
- Enable alerting for verified-share regression.

### Phase 3: Optimize for Conversion

- Improve clustering/domain normalization to convert more candidates from Lane B to Lane A.
- Tune policy thresholds by topic class and source availability.
- Lock success criteria for steady-state operation.

## 6) Risk Register

- **Throughput degradation:** mitigated via Lane B fallback and staged enforcement.
- **Coverage gaps in sparse topics:** mitigated via topic-aware thresholds and transparent caveats.
- **Metric gaming risk:** mitigated by tracking both volume and trust-weighted quality KPIs.

## 7) Success Criteria

Refactor is considered successful when all are met for a sustained period:

- Verified-share reaches agreed target band.
- Median unique-domain count increases without severe latency regression.
- Backlog drain remains stable or improves.
- Retention/revisit metrics improve for verified stories.

## 8) Governance and Controls

- Runtime-config keys must support rollback by version.
- Changes to quality thresholds require reason-tagged audit entries.
- Production rollout gates require dashboard sign-off from ops and product.

## 9) Minimal Implementation Scope

This proposal intentionally limits MVP scope to:

- lane metadata,
- threshold policy routing,
- observability + audit fields,
- phased guardrails.

No broad UI redesign or unrelated agent rewrites are required for first delivery.
