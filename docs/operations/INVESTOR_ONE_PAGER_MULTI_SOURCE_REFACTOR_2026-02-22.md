# Investor One-Pager: Multi-Source Integrity Refactor

**Date:** 2026-02-22  
**Program:** JustNews Living Stories  
**Audience:** Stakeholders, investors, and product leadership

## Executive Summary

JustNews currently produces output at high throughput, but the publication mix is overly singleton-heavy (single-source stories), which weakens trust and differentiation in a market where cross-source verification is the core value proposition. This refactor aligns product behavior with mission by introducing a dual-lane publication model and explicit quality gates for multi-source story integrity.

The objective is to preserve velocity while materially increasing the percentage of published stories that are evidence-backed across independent domains.

## Why This Matters Now

- Current pipeline behavior and policy settings prioritize throughput in ways that allow singleton publication to dominate.
- Discovery and clustering constraints can leave high-volume pools underutilized when strict source-diversity thresholds are unmet.
- This creates a credibility gap between platform positioning (cross-source reliability) and observed output composition.

## Refactor Goal

Increase **trust-weighted output quality** without collapsing throughput by:

1. Separating singleton and multi-source publication paths.
2. Making multi-source verification the default target lane.
3. Restricting singleton publication to clearly labeled, lower-confidence briefs.
4. Measuring success with quality and retention KPIs, not only output volume.

## Target State (MVP)

### 1) Dual-Lane Publishing

- **Lane A — Multi-Source Story (Primary):** Requires cross-domain corroboration and higher editorial confidence.
- **Lane B — Singleton Brief (Fallback):** Allowed for timeliness, but explicitly labeled and excluded from “verified story” metrics.

### 2) Explicit Quality Gates

- Minimum independent domain count for Lane A.
- Contradiction/consistency checks before publish.
- Provenance trace retained for auditability.

### 3) Transparent User Experience

- Clear badges for “multi-source verified” vs “single-source developing”.
- Structured caveats where confidence is lower.

## Expected Business Impact

- Stronger trust and defensibility in product narrative.
- Better audience retention for Living Stories due to perceived reliability.
- Clearer enterprise/API value proposition for downstream consumers requiring provenance and confidence metadata.
- Lower strategic risk from claim/behavior mismatch.

## KPI Framework

### Quality KPIs

- Multi-source share of published stories.
- Median unique-source count per published story.
- Contradiction flags per 100 published stories.

### Product KPIs

- Living Story revisit rate (7-day/30-day).
- Session depth on verified stories.
- Time-to-trust (first reliable cross-source update).

### Operational KPIs

- Backlog drain rate for candidate pools.
- Lane A pass-through rate.
- Singleton-to-multi-source conversion rate over time.

## Phased Delivery

### Phase 1 (2–3 weeks): Control + Instrumentation

- Introduce lane assignment logic and metrics.
- Add labels and confidence metadata to output.
- Deploy dashboards for source-diversity and lane mix.

### Phase 2 (3–5 weeks): Policy Tightening

- Raise Lane A thresholds gradually.
- Improve clustering and source-normalization quality.
- Add automated alerts for quality regression.

### Phase 3 (2–4 weeks): Product Hardening

- Tune ranking/recommendations to favor verified stories.
- Stabilize SLAs and publish external quality reporting.

## Risks and Mitigations

- **Risk:** Throughput dips while quality gates tighten.  
  **Mitigation:** Dual-lane fallback preserves timeliness while quality ramps.

- **Risk:** Sparse-source topics underperform.  
  **Mitigation:** Topic-aware thresholds and explicit “developing” status.

- **Risk:** Operational complexity increases.  
  **Mitigation:** Incremental rollout with observability-first controls.

## Investment Ask

Approve the multi-source integrity refactor as a prioritized platform initiative with KPI-governed rollout. This is a quality-and-trust compounding investment that protects brand credibility, improves retention, and strengthens enterprise monetization pathways.

## Decision Gate

Proceed to implementation when all are true:

- KPI dashboard instrumentation is in place.
- Dual-lane policy can be toggled per environment.
- Rollback path for quality gate changes is validated.
