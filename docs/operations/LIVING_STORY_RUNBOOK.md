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

## Current Implementation (Phase-1 + Phase-2/3 Hardening)

Phase-1 behavior is implemented in:

- `agents/workflow_orchestrator/policies.py`
- `agents/chief_editor/tools.py`

### What is implemented

1. **Canonical per-cluster story upsert**
   - `ClusterToSynthesisPolicy` and `HeavyClusterRetryPolicy` call a shared upsert path.
   - The latest story for `cluster_id` is updated in-place when appropriate.

2. **Meaningful-change gating**
   - Computes text similarity delta and source/article delta.
   - Computes weighted composite score (text + source diversity + recency + fact quality + new article pressure).
   - Applies threshold rules and operator overrides.

3. **Action outcomes**
   - `action=updated` (meaningful):
     - story content updated,
     - `is_published` reset to `0`,
     - `critique_status` reset to `pending`,
     - `critique_text` cleared.
    - `action=tracked_noop` (not meaningful):
     - metadata + input tracking updated,
     - no critique/publish reset.
    - Forced actions:
       - `action=forced_update`
       - `action=forced_hold`
       - `action=forced_republish`

4. **Revision metadata persisted** (`synthesized_articles.synth_metadata`)
   - `living_story.revision`
   - `living_story.input_fingerprint`
   - `living_story.last_meaningful_score`
   - `living_story.last_composite_score`
   - `living_story.last_new_articles`
   - `living_story.last_update_action`
   - `living_story.updated_at`
   - `living_story.last_diff`
   - `living_story.explainability`
   - `living_story.telemetry`

5. **Publish conflict reduction**
   - Workflow no longer double-writes publish state.
   - Chief Editor marks publish state with idempotent guard (`... WHERE is_published = 0`).

---

## Decision Logic (Meaningful vs No-op)

The gate evaluates:

- text delta (`1 - similarity(previous_body, new_body)`),
- count of newly-added input articles,
- weighted composite score,
- configurable thresholds.

Default rules:

- meaningful if text delta >= `LIVING_STORY_MAJOR_TEXT_DELTA` (default `0.12`), OR
- meaningful if new articles exist AND text delta >= `LIVING_STORY_MINOR_TEXT_DELTA` (default `0.03`), OR
- meaningful if new article count >= `LIVING_STORY_MIN_NEW_ARTICLES` (default `2`).
- meaningful if weighted composite score >= `LIVING_STORY_COMPOSITE_THRESHOLD` (default `0.35`).

Weighted components (defaults):

- `LIVING_STORY_WEIGHT_TEXT=0.45`
- `LIVING_STORY_WEIGHT_SOURCE=0.20`
- `LIVING_STORY_WEIGHT_RECENCY=0.15`
- `LIVING_STORY_WEIGHT_FACT=0.15`
- `LIVING_STORY_WEIGHT_NEW_ARTICLES=0.05`

Otherwise: `tracked_noop`.

Operator override controls can replace the decision with:

- `force_update`
- `force_hold`
- `force_republish`

---

## Environment Variables

Living-story controls:

- `LIVING_STORY_MAJOR_TEXT_DELTA` (default `0.12`)
- `LIVING_STORY_MINOR_TEXT_DELTA` (default `0.03`)
- `LIVING_STORY_MIN_NEW_ARTICLES` (default `2`)
- `LIVING_STORY_COMPOSITE_THRESHOLD` (default `0.35`)
- `LIVING_STORY_WEIGHT_TEXT` (default `0.45`)
- `LIVING_STORY_WEIGHT_SOURCE` (default `0.20`)
- `LIVING_STORY_WEIGHT_RECENCY` (default `0.15`)
- `LIVING_STORY_WEIGHT_FACT` (default `0.15`)
- `LIVING_STORY_WEIGHT_NEW_ARTICLES` (default `0.05`)
- `LIVING_STORY_OPERATOR_OVERRIDES_JSON` (default empty JSON)
- `LIVING_STORY_SCORE_WINDOW` (default `50`)
- `LIVING_STORY_PUBLISH_LATENCY_WINDOW` (default `30`)
- `LIVING_STORY_OVERRIDE_REQUIRE_OWNER` (default `1`)
- `LIVING_STORY_OVERRIDE_REQUIRE_APPROVAL` (default `0`)
- `LIVING_STORY_OVERRIDE_MAX_TTL_HOURS` (default `168`)
- `LIVING_STORY_CALIBRATION_PROFILE` (default `balanced`)
- `LIVING_STORY_RECENCY_MULTIPLIER_BREAKING` (default `1.35`)
- `LIVING_STORY_RECENCY_MULTIPLIER_ACTIVE` (default `1.0`)
- `LIVING_STORY_RECENCY_MULTIPLIER_BACKGROUND` (default `0.8`)
- `LIVING_STORY_THRESHOLD_MULTIPLIER_BREAKING` (default `0.85`)
- `LIVING_STORY_THRESHOLD_MULTIPLIER_ACTIVE` (default `1.0`)
- `LIVING_STORY_THRESHOLD_MULTIPLIER_BACKGROUND` (default `1.1`)

Set these in `global.env` to tune editorial sensitivity.

Example operator overrides:

```bash
LIVING_STORY_OPERATOR_OVERRIDES_JSON='{
   "CL-1234abcd": {"action": "force_update", "reason": "major developing event"},
   "STORY-6d921889": "force_republish"
}'
```

Governance expectations for override payload entries:

- `owner` (required by default),
- optional `approved_by` (required if `LIVING_STORY_OVERRIDE_REQUIRE_APPROVAL=1`),
- optional `expires_at` (must not exceed `LIVING_STORY_OVERRIDE_MAX_TTL_HOURS`).

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

### 4) Validate telemetry and explainability payload

```sql
SELECT
   JSON_EXTRACT(synth_metadata, '$.living_story.last_update_action') AS action,
   JSON_EXTRACT(synth_metadata, '$.living_story.last_composite_score') AS composite_score,
   JSON_EXTRACT(synth_metadata, '$.living_story.telemetry.decision_counts') AS decision_counts,
   JSON_EXTRACT(synth_metadata, '$.living_story.telemetry.mean_publish_latency_seconds') AS mean_publish_latency,
   JSON_EXTRACT(synth_metadata, '$.living_story.explainability.reasons') AS reasons,
   JSON_EXTRACT(synth_metadata, '$.living_story.last_diff') AS diff_snapshot
FROM synthesized_articles
WHERE cluster_id = '<CLUSTER_ID>'
ORDER BY updated_at DESC, id DESC
LIMIT 1;
```

### 5) Generate operator dashboard report artifact

```bash
/app/.venv/bin/python scripts/ops/living_story_dashboard_report.py \
   --limit 500 \
   --json-out /tmp/living_story_report.json \
   --md-out /tmp/living_story_report.md
```

This report summarizes action distribution, calibration profile usage, override rejections, and publish-latency trends.

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
- inspect `living_story.last_composite_score` and `living_story.explainability.reasons`.
- check whether `force_hold` override is active for cluster/story.

### Symptom: excessive republishing churn

Potential causes:

- thresholds too permissive.

Actions:

- increase `LIVING_STORY_MAJOR_TEXT_DELTA` and/or `LIVING_STORY_MINOR_TEXT_DELTA`,
- increase `LIVING_STORY_MIN_NEW_ARTICLES`.
- increase `LIVING_STORY_COMPOSITE_THRESHOLD`.
- reduce any aggressive `force_republish` overrides.
- switch to `LIVING_STORY_CALIBRATION_PROFILE=conservative` for stricter defaults.

### Symptom: overrides are ignored

Potential causes:

- missing `owner` when owner governance is enabled,
- missing `approved_by` when approval governance is enabled,
- expired or overlong `expires_at` TTL.

Actions:

- inspect `living_story.explainability.override_rejected` payload,
- correct override entry and re-run synthesis cycle.

### Symptom: publish latency is rising after meaningful updates

Actions:

- inspect `living_story.telemetry.publish_latency_recent_seconds`.
- verify critique/publish queue depth and retry behavior.
- tune batch sizes or isolate heavy clusters when publish queue backs up.

---

## Editorial Governance Recommendations

For production hardening:

1. Add override expiry/approval governance for forced actions.
2. Add editorial dashboards for explainability and churn monitoring.
3. Calibrate composite weights using production revision outcomes.
4. Add alerting on unusual spikes in forced overrides or publish latency.

---

## Related Docs

- `docs/LIVING_STORIES_ARCHITECTURE.md`
- `docs/LIVING_STORIES_IMPLEMENTATION_PLAN.md`
- `docs/orchestrator/WORKFLOW_ORCHESTRATOR.md`
- `docs/operations/TROUBLESHOOTING.md`