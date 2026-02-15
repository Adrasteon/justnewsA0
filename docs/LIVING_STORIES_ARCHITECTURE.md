# Living Stories Architecture (Phase-1, Current)

## Overview

Living Stories implement a **canonical narrative per cluster**: one story identity evolves over time as new reporting arrives.

The architecture prioritizes:

1. **Continuity**: avoid duplicate story objects for the same event cluster.
2. **Meaningful change**: re-run critique/publish only when updates materially change the narrative.
3. **Operational safety**: publish is idempotent under retries and concurrent pipeline activity.

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
- configured thresholds.

If meaningful:

- update body/title/metadata,
- reset `critique_status` to `pending`,
- clear critique text,
- set `is_published = 0` to trigger republish.

If not meaningful:

- persist tracking metadata only,
- keep critique/publish states unchanged (`tracked_noop`).

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

Phase-1 metadata contract:

- `revision`
- `input_fingerprint`
- `last_meaningful_score`
- `last_new_articles`
- `last_update_action` (`updated` or `tracked_noop`)
- `updated_at`

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

---

## End-to-End Lifecycle

1. Articles are analyzed, embedded, fact-checked, and clustered.
2. Synthesis generates a candidate narrative for a cluster.
3. Living-story gate evaluates significance against previous canonical version.
4. Meaningful updates re-enter critique/publish flow; non-meaningful updates are tracked without churn.
5. Published canonical story evolves across revisions while preserving `story_id` continuity.

---

## Operational Notes

- This document reflects current Phase-1 implementation.
- For commands and day-2 diagnostics, see `docs/operations/LIVING_STORY_RUNBOOK.md`.
- For roadmap and future phases, see `docs/LIVING_STORIES_IMPLEMENTATION_PLAN.md`.
