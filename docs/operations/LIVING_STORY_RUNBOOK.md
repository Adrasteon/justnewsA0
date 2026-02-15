# Living Story Runbook

## Purpose

This runbook defines how JustNews maintains **Living Stories**: continuously evolving articles that are updated only when new evidence meaningfully changes the narrative.

This is the operational reference for:

- living-story philosophy and editorial intent,
- workflow lifecycle and state transitions,
- meaningful-change decision logic,
- publish idempotency and conflict avoidance,
- diagnostics and recovery.

---

## Living Story Philosophy

A Living Story is not a one-time snapshot. It is a canonical narrative for an event/topic that evolves as new reporting arrives.

Core principles:

1. **Continuity over fragmentation**
   - Keep one canonical story for a cluster/topic.
   - Avoid creating duplicate stories for incremental updates.

2. **Meaningful updates only**
   - New articles do not automatically imply republishing.
   - Republish only when new evidence changes the substance of the narrative.

3. **Editorial quality gates**
   - Meaningful updates return to critique + publish workflow.
   - Non-meaningful updates are tracked for auditability, but do not churn public output.

4. **Idempotent publishing**
   - Publish operations must be safe under retries/re-entrancy.
   - Duplicate publish attempts should resolve as success/no-op, not failures.

---

## Current Phase-1 Implementation (Production Behavior)

Phase-1 behavior is implemented in:

- `agents/workflow_orchestrator/policies.py`
- `agents/chief_editor/tools.py`

### What Phase-1 does

1. **Canonical per-cluster story upsert**
   - `ClusterToSynthesisPolicy` and `HeavyClusterRetryPolicy` call a shared upsert path.
   - The latest story for `cluster_id` is updated in-place when appropriate.

2. **Meaningful-change gating**
   - Computes text similarity delta and source/article delta.
   - Decides whether the update is meaningful.

3. **Action outcomes**
   - `action=updated` (meaningful):
     - story content updated,
     - `is_published` reset to `0`,
     - `critique_status` reset to `pending`,
     - `critique_text` cleared.
   - `action=tracked_noop` (not meaningful):
     - metadata + input tracking updated,
     - no critique/publish reset.

4. **Revision metadata persisted** (`synthesized_articles.synth_metadata`)
   - `living_story.revision`
   - `living_story.input_fingerprint`
   - `living_story.last_meaningful_score`
   - `living_story.last_new_articles`
   - `living_story.last_update_action`
   - `living_story.updated_at`

5. **Publish conflict reduction**
   - Workflow no longer double-writes publish state.
   - Chief Editor marks publish state with idempotent guard (`... WHERE is_published = 0`).

---

## Decision Logic (Meaningful vs No-op)

The Phase-1 gate evaluates:

- text delta (`1 - similarity(previous_body, new_body)`),
- count of newly-added input articles,
- configurable thresholds.

Default rules:

- meaningful if text delta >= `LIVING_STORY_MAJOR_TEXT_DELTA` (default `0.12`), OR
- meaningful if new articles exist AND text delta >= `LIVING_STORY_MINOR_TEXT_DELTA` (default `0.03`), OR
- meaningful if new article count >= `LIVING_STORY_MIN_NEW_ARTICLES` (default `2`).

Otherwise: `tracked_noop`.

---

## Environment Variables

Current Phase-1 living-story controls:

- `LIVING_STORY_MAJOR_TEXT_DELTA` (default `0.12`)
- `LIVING_STORY_MINOR_TEXT_DELTA` (default `0.03`)
- `LIVING_STORY_MIN_NEW_ARTICLES` (default `2`)

Set these in `global.env` to tune editorial sensitivity.

---

## End-to-End Lifecycle

1. **Ingestion/Analysis/Embedding**
   - article enters pipeline, gets analyzed and embedded.

2. **Fact-check + Clustering**
   - article associated with a cluster.

3. **Synthesis (Living Story gate)**
   - synthesizer produces candidate body.
   - upsert logic determines `updated` vs `tracked_noop`.

4. **Critique + Publish**
   - runs only for meaningful updates (`updated` path resets states).
   - publish is idempotent.

5. **Public article refresh**
   - canonical published entry can be updated when meaningful change occurs.

---

## Operational Verification

### 1) Verify living-story actions in logs

```bash
grep -Ein 'Upserted living story|no meaningful story delta|tracked inputs without republish' /tmp/justnews_services_logs/workflow_orchestrator.startup.log | tail -n 50
```

### 2) Verify publish conflict signature is absent

```bash
grep -Ein "Record has changed since last read" /tmp/justnews_services_logs/workflow_orchestrator.startup.log | tail -n 20
```

### 3) Inspect story metadata for a cluster

```sql
SELECT story_id, cluster_id, is_published, critique_status, updated_at, synth_metadata
FROM synthesized_articles
WHERE cluster_id = '<CLUSTER_ID>'
ORDER BY updated_at DESC, id DESC
LIMIT 1;
```

Confirm `synth_metadata.living_story` fields exist and revision increments over meaningful updates.

---

## Troubleshooting

### Symptom: repeated publish conflicts (`1020 HY000`)

Potential causes:

- multiple writers toggling `is_published` for same story,
- concurrent publish retries without idempotent guards.

Checks:

- ensure workflow policy does not directly set publish flag,
- confirm chief-editor update uses `WHERE is_published = 0`.

### Symptom: no living-story updates despite new articles

Potential causes:

- thresholds too strict,
- cluster assignment not receiving new article members,
- synthesis body too similar for configured deltas.

Actions:

- lower `LIVING_STORY_MINOR_TEXT_DELTA` or `LIVING_STORY_MIN_NEW_ARTICLES`,
- verify `input_cluster_ids` growth for target cluster,
- inspect `living_story.last_new_articles` and `last_meaningful_score`.

### Symptom: excessive republishing churn

Potential causes:

- thresholds too permissive.

Actions:

- increase `LIVING_STORY_MAJOR_TEXT_DELTA` and/or `LIVING_STORY_MINOR_TEXT_DELTA`,
- increase `LIVING_STORY_MIN_NEW_ARTICLES`.

---

## Editorial Governance Recommendations

For production hardening:

1. Add a periodic report of `tracked_noop` vs `updated` decisions by cluster.
2. Add HITL override for forced update / forced hold.
3. Add source-diversity weighting into meaningful score.
4. Add revision diff snapshots (title/body delta summary) for newsroom transparency.

---

## Related Docs

- `docs/LIVING_STORIES_ARCHITECTURE.md`
- `docs/LIVING_STORIES_IMPLEMENTATION_PLAN.md`
- `docs/orchestrator/WORKFLOW_ORCHESTRATOR.md`
- `docs/operations/TROUBLESHOOTING.md`