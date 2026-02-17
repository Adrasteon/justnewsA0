# JustNews Living Stories Implementation Plan

**Status:** Active roadmap (updated to current implementation)

This plan tracks what is already in production behavior and what remains for future phases.

---

## 1) Objective

Deliver a newsroom-safe Living Story system where each cluster evolves as one canonical story, and republishing occurs only when updates are editorially meaningful.

---

## 2) Phase-1 (Implemented)

Phase-1 is implemented in orchestrator + chief-editor tooling.

### Delivered capabilities

1. **Canonical per-cluster upsert**
    - Synthesis reuses an existing cluster story instead of creating duplicates.

2. **Meaningful-change gating**
    - Update significance is computed from text delta + new article inputs.
    - Non-meaningful updates are tracked as no-op revisions.

3. **State-safe repipeline behavior**
    - Meaningful updates reset critique/publish state.
    - Non-meaningful updates avoid critique/publish churn.

4. **Metadata and revision tracking**
    - `synth_metadata.living_story` stores revision/fingerprint/decision fields.

5. **Publish idempotency hardening**
    - Publish mark uses guarded update and returns `published_already` when retried.

### Phase-1 config knobs

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `LIVING_STORY_MAJOR_TEXT_DELTA` | `0.12` | Always-meaningful text-change threshold. |
| `LIVING_STORY_MINOR_TEXT_DELTA` | `0.03` | Text-change threshold that can be meaningful with new sources. |
| `LIVING_STORY_MIN_NEW_ARTICLES` | `2` | New-source count that can independently force meaningful update. |

---

## 3) Phase-2 (Implemented)

Focus achieved: decision quality and operator visibility.

### Delivered hardening

1. Decision telemetry (per cluster):
    - `decision_counts` (including `updated`, `tracked_noop`, and forced actions),
    - rolling mean/median meaningful score,
    - publish latency telemetry (recent window + mean/median).

2. Revision diff summaries:
    - title/body similarity + delta,
    - source additions/removals snapshot,
    - body length deltas.

3. Operator override controls:
    - `force_update`,
    - `force_hold`,
    - `force_republish`,
    - supported through `synth_metadata` override payloads and `LIVING_STORY_OPERATOR_OVERRIDES_JSON`.

---

## 4) Phase-3 (Implemented Core)

Focus: richer editorial semantics and stronger trust guarantees.

### Delivered now

1. Source-diversity weighting in meaningful score.
2. Temporal recency weighting in meaningful score.
3. Fact-quality weighting in meaningful score.
4. Policy-level explainability payload persisted per decision.

### Remaining roadmap

1. Ongoing calibration refinement from production outcomes (policy tuning, not missing functionality).
2. Editorial UI surfacing for explainability in dashboard products.

---

## 5) Phase-4 (Implemented: Governance + Operator Reporting)

Focus achieved: strong operator controls and auditable operational insight.

### Delivered

1. Override governance:
    - owner/approver/expiry fields supported,
    - configurable enforcement for owner and approval requirements,
    - TTL guardrails and expired-override rejection tracking.

2. Urgency-aware calibration:
    - urgency class inference (`breaking`, `active`, `background`),
    - calibration profiles (`balanced`, `conservative`, `aggressive`, `breaking`),
    - per-urgency recency and threshold multipliers.

3. Operator reporting artifact:
    - `scripts/ops/living_story_dashboard_report.py` generates JSON/Markdown telemetry reports,
    - summarizes actions, scores, override usage/rejections, and publish-latency trends.

---

## 6) Validation Criteria

Current success criteria are validated when:

1. Canonical continuity:
    - same cluster maintains stable `story_id` across updates.

2. Churn control:
    - non-meaningful updates do not trigger critique/publish resets.

3. Meaningful responsiveness:
    - meaningful updates reliably return to critique/publish.

4. Conflict resilience:
    - publish retries resolve idempotently (no recurring `1020` conflict loops).

---

## 7) Risks and Mitigations

1. **Over-sensitive thresholds** → noisy republish churn
    - Mitigation: raise text/new-article thresholds.

2. **Under-sensitive thresholds** → missed meaningful updates
    - Mitigation: lower thresholds and audit `tracked_noop` clusters.

3. **Concurrent writers on publish state**
    - Mitigation: keep single publish ownership + idempotent write guard.

---

## 8) Related Documents

- `docs/LIVING_STORIES_ARCHITECTURE.md`
- `docs/operations/LIVING_STORY_RUNBOOK.md`
- `docs/orchestrator/WORKFLOW_ORCHESTRATOR.md`

