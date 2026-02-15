# Living Stories Architecture (Phase-1 + Phase-2/3 Hardening)

## Overview

Living Stories implement a **canonical narrative per cluster**: one story identity evolves over time as new reporting arrives.

The architecture prioritizes:

1. **Continuity**: avoid duplicate story objects for the same event cluster.
2. **Meaningful change**: re-run critique/publish only when updates materially change the narrative.
3. **Operational safety**: publish is idempotent under retries and concurrent pipeline activity.
4. **Operator control + explainability**: editorial overrides and decision traces are persisted for auditability.

---

## Core Design

### Canonical Story Identity

- Canonical identity is anchored by `cluster_id` in `synthesized_articles`.
- For each cluster, synthesis uses an upsert path:
  - update existing latest story when cluster already has a canonical story,
  - insert a new row only when no prior story exists for that cluster.

### Meaningful-Change Gating

Each new synthesis candidate is compared with the previous canonical body and input set.

Decision signals:

- text delta (`1 - similarity(previous, candidate)`),
- number of newly-added source articles for the cluster,
- weighted contextual score (source diversity, recency, fact-quality, new-article pressure),
- configured thresholds and operator overrides.

If meaningful:

- update body/title/metadata,
- reset `critique_status` to `pending`,
- clear critique text,
- set `is_published = 0` to trigger republish.

If not meaningful:

- persist tracking metadata only,
- keep critique/publish states unchanged (`tracked_noop`).

### Operator Overrides (HITL Control)

Living Story decision logic supports explicit operator actions:

- `force_update`
- `force_hold`
- `force_republish`

Overrides can be provided via:

- `synth_metadata.living_story.operator_override`, or
- `LIVING_STORY_OPERATOR_OVERRIDES_JSON` map in environment.

Override usage is persisted in explainability metadata for audit.

Governance controls are enforced through environment policy:

- owner required (`LIVING_STORY_OVERRIDE_REQUIRE_OWNER`),
- optional approver requirement (`LIVING_STORY_OVERRIDE_REQUIRE_APPROVAL`),
- max override TTL (`LIVING_STORY_OVERRIDE_MAX_TTL_HOURS`).

Rejected overrides are captured in explainability payloads.

### Urgency-Aware Calibration

Decision scoring supports urgency-class calibration:

- urgency classes: `breaking`, `active`, `background`,
- profile selection: `LIVING_STORY_CALIBRATION_PROFILE`,
- per-urgency multipliers:
  - `LIVING_STORY_RECENCY_MULTIPLIER_<CLASS>`
  - `LIVING_STORY_THRESHOLD_MULTIPLIER_<CLASS>`

This enables conservative behavior for background updates and faster response for developing stories.

### Publish Idempotency

- Publish state transitions are handled with a guarded update in Chief Editor tools.
- Duplicate publish attempts become a no-op (`published_already`) rather than a conflict failure.
- Workflow policy avoids duplicate publish-state writes.

---

## Data Model Usage (Current)

### `synthesized_articles`

Primary store for canonical living stories.

Operational fields:

- `story_id`, `cluster_id`
- `is_published`
- `critique_status`, `critique_text`
- `synth_metadata` (JSON)

### `synth_metadata.living_story`

Current metadata contract includes:

- `revision`
- `input_fingerprint`
- `last_meaningful_score`
- `last_composite_score`
- `last_new_articles`
- `last_update_action` (`updated`, `tracked_noop`, `forced_update`, `forced_hold`, `forced_republish`)
- `updated_at`
- `last_diff` (title/body/source delta summary)
- `explainability` (decision reasons, thresholds, weights, component scores, override source)
- `telemetry`
  - `decision_counts`
  - `meaningful_scores_recent`
  - `mean_meaningful_score` / `median_meaningful_score`
  - `publish_latency_recent_seconds`
  - `last_publish_latency_seconds`
  - `mean_publish_latency_seconds` / `median_publish_latency_seconds`

### Supporting Inputs

- `news_article` provides source inputs per cluster.
- `articles` and memory/chroma flows provide embeddings and cluster assignment prerequisites.

---

## Workflow Placement

Living-story behavior is executed in synthesis-stage orchestrator policies:

- `ClusterToSynthesisPolicy`
- `HeavyClusterRetryPolicy`

Both use shared upsert + meaningful-gate logic before any critique/publish resets.

---

## Configuration (`global.env`)

| Variable | Default | Role |
| :--- | :--- | :--- |
| `LIVING_STORY_MAJOR_TEXT_DELTA` | `0.12` | Large text change threshold that is always meaningful. |
| `LIVING_STORY_MINOR_TEXT_DELTA` | `0.03` | Smaller text delta that can be meaningful when supported by new sources. |
| `LIVING_STORY_MIN_NEW_ARTICLES` | `2` | Minimum number of new source articles that can force a meaningful update. |
| `LIVING_STORY_COMPOSITE_THRESHOLD` | `0.35` | Threshold for weighted composite meaningful score. |
| `LIVING_STORY_WEIGHT_TEXT` | `0.45` | Weight for text-delta component in composite score. |
| `LIVING_STORY_WEIGHT_SOURCE` | `0.20` | Weight for source-diversity component in composite score. |
| `LIVING_STORY_WEIGHT_RECENCY` | `0.15` | Weight for recency component in composite score. |
| `LIVING_STORY_WEIGHT_FACT` | `0.15` | Weight for fact-quality component in composite score. |
| `LIVING_STORY_WEIGHT_NEW_ARTICLES` | `0.05` | Weight for new-article-pressure component in composite score. |
| `LIVING_STORY_OPERATOR_OVERRIDES_JSON` | `{}` | Optional cluster/story override map (`force_update` / `force_hold` / `force_republish`). |
| `LIVING_STORY_OVERRIDE_REQUIRE_OWNER` | `1` | Require owner field in override payload. |
| `LIVING_STORY_OVERRIDE_REQUIRE_APPROVAL` | `0` | Require approved_by field in override payload. |
| `LIVING_STORY_OVERRIDE_MAX_TTL_HOURS` | `168` | Maximum allowed override TTL horizon. |
| `LIVING_STORY_CALIBRATION_PROFILE` | `balanced` | Calibration preset (`balanced`, `conservative`, `aggressive`, `breaking`). |
| `LIVING_STORY_RECENCY_MULTIPLIER_BREAKING` | `1.35` | Recency weight multiplier for breaking stories. |
| `LIVING_STORY_RECENCY_MULTIPLIER_ACTIVE` | `1.0` | Recency weight multiplier for active stories. |
| `LIVING_STORY_RECENCY_MULTIPLIER_BACKGROUND` | `0.8` | Recency weight multiplier for background stories. |
| `LIVING_STORY_THRESHOLD_MULTIPLIER_BREAKING` | `0.85` | Composite threshold multiplier for breaking stories. |
| `LIVING_STORY_THRESHOLD_MULTIPLIER_ACTIVE` | `1.0` | Composite threshold multiplier for active stories. |
| `LIVING_STORY_THRESHOLD_MULTIPLIER_BACKGROUND` | `1.1` | Composite threshold multiplier for background stories. |

---

## End-to-End Lifecycle

1. Articles are analyzed, embedded, fact-checked, and clustered.
2. Synthesis generates a candidate narrative for a cluster.
3. Living-story gate evaluates significance against previous canonical version.
4. Meaningful updates re-enter critique/publish flow; non-meaningful updates are tracked without churn.
5. Published canonical story evolves across revisions while preserving `story_id` continuity.

---

## Operational Notes

- This document reflects current implementation including Phase-2/3 hardening controls.
- For commands and day-2 diagnostics, see `docs/operations/LIVING_STORY_RUNBOOK.md`.
- For roadmap and future phases, see `docs/LIVING_STORIES_IMPLEMENTATION_PLAN.md`.
