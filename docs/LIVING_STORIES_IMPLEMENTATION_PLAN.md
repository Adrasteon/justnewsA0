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

## 3) Phase-2 (Next)

Focus: improve decision quality and operator visibility.

### Planned work

1. Add explicit decision telemetry (per cluster):
    - `updated` vs `tracked_noop` counters,
    - mean/median meaningful score,
    - publish latency post-meaningful change.

2. Add revision diff summaries:
    - lightweight title/body delta for each revision,
    - source additions/removals snapshot.

3. Add operator override controls (HITL):
    - force-update,
    - force-hold,
    - force-republish.

---

## 4) Phase-3 (Future)

Focus: richer editorial semantics and stronger trust guarantees.

### Planned work

1. Source-diversity weighting in meaningful score.
2. Temporal recency weighting (breaking vs background updates).
3. Fact-quality weighting (confidence-aware update promotion).
4. Policy-level explainability payload for every living-story decision.

---

## 5) Validation Criteria

Phase-1 success is validated when:

1. Canonical continuity:
    - same cluster maintains stable `story_id` across updates.

2. Churn control:
    - non-meaningful updates do not trigger critique/publish resets.

3. Meaningful responsiveness:
    - meaningful updates reliably return to critique/publish.

4. Conflict resilience:
    - publish retries resolve idempotently (no recurring `1020` conflict loops).

---

## 6) Risks and Mitigations

1. **Over-sensitive thresholds** → noisy republish churn
    - Mitigation: raise text/new-article thresholds.

2. **Under-sensitive thresholds** → missed meaningful updates
    - Mitigation: lower thresholds and audit `tracked_noop` clusters.

3. **Concurrent writers on publish state**
    - Mitigation: keep single publish ownership + idempotent write guard.

---

## 7) Related Documents

- `docs/LIVING_STORIES_ARCHITECTURE.md`
- `docs/operations/LIVING_STORY_RUNBOOK.md`
- `docs/orchestrator/WORKFLOW_ORCHESTRATOR.md`

