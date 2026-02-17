# Workflow Orchestrator

The Workflow Orchestrator (`agents/workflow_orchestrator`) executes business-stage transitions for JustNews. It continuously evaluates policy predicates, advances eligible records, and dispatches MCP tool calls to agents.

## Core Responsibilities

1. Move articles through analysis, embedding, fact-check, clustering, synthesis, critique, and publish readiness.
2. Prevent stage starvation with policy retries and bounded batching.
3. Coordinate heavy-cluster retries without blocking normal throughput.
4. Apply Living Story semantics at synthesis time.

## Core Policies (Current)

- `IngestionToAnalysisPolicy`
- `AnalysisToEmbeddingPolicy`
- `AnalysisToSummaryPolicy` *(optional; disabled by default via `ORCHESTRATOR_ENABLE_SOURCE_SUMMARY_STAGE=0`)*
- `SummaryToFactCheckPolicy` *(fact-check gating no longer depends on per-source summary presence)*
- `FactCheckToClusterPolicy`
- `ClusterToSynthesisPolicy`
- `HeavyClusterRetryPolicy`
- `SynthesisToCritiquePolicy`
- `CritiqueToPublishingPolicy`

Policy registration and ordering are defined in `agents/workflow_orchestrator/engine.py`.

## Living Story Behavior in Orchestrator

Living Story logic is applied in synthesis policies (`ClusterToSynthesisPolicy`, `HeavyClusterRetryPolicy`):

1. Resolve canonical story row for `cluster_id`.
2. Synthesize candidate content.
3. Evaluate meaningful-change score (text + source-input deltas).
4. Persist either:
   - meaningful `updated` result (reset critique/publish states), or
   - non-meaningful `tracked_noop` (metadata-only progression).

Synthesis payload contract now separates:

- `body`: full synthesized article body used for publication detail pages
- `summary`: short abstract used for cards/SEO previews

This ensures one evolving story identity per cluster and prevents unnecessary republish churn.

## Publish Ownership and Idempotency

- Orchestrator no longer performs duplicate publish-state writes after publish success.
- Publish-state mark is owned by Chief Editor tooling with guarded SQL updates.
- Re-entrant publish attempts should produce idempotent outcomes (`published_already`) rather than conflict loops.

## Heavy Cluster Management

`HeavyClusterRetryPolicy` isolates large/expensive clusters from the normal fast loop so large synthesis jobs do not block smaller cluster throughput.

Operational pattern:

1. normal policy processes regular work,
2. heavy clusters are deferred when needed,
3. retry policy re-attempts under lower-load conditions.

## Operational References

- `docs/LIVING_STORIES_ARCHITECTURE.md`
- `docs/operations/LIVING_STORY_RUNBOOK.md`
- `docs/operations/TROUBLESHOOTING.md`
