# Two-Lane Traceability Implementation Plan

Date: 2026-03-20
Status: Planning baseline
Audience: Product, engineering, operations

## Objective

Implement the intended two-lane crawl workflow plus full entity, statement, and quote traceability using incremental changes on top of the current crawler, analyst, orchestrator, critic, and transparency infrastructure.

This plan makes four user decisions operational:

- Lane 1 must start from BBC seed articles and use DuckDuckGo full-web expansion per seed article.
- Balance policy is hybrid: broad perspective coverage with explicit material-side checks where needed.
- Opinion is included, but must be attributed and labeled.
- Attribution storage uses dedicated normalized tables rather than prompt-only or JSON-only metadata.

## Target Behavior

### Lane 1

1. Crawl BBC and stop after 10 newly ingested seed articles.
2. For each seed article, derive open-web search intents.
3. Use DuckDuckGo to find up to 5 corroborating or contrasting articles per seed.
4. Ingest those follow-up articles with explicit seed-to-result provenance.
5. Cluster, analyze, and synthesize using structured attributed speech rather than untracked snippets.

### Lane 2

1. Remain a fallback or secondary retrieval lane.
2. Activate only after current work is sufficiently drained or other configured exhaustion conditions are met.
3. Crawl a broader source set with bounded per-site budgets.
4. Preserve current verified-story versus developing-brief publication semantics while separating them from retrieval-lane orchestration.

### Traceability and Governance

1. Preserve who said what, in what form, from which source, and with what confidence.
2. Link statements and quotes to entities, source articles, and living stories.
3. Distinguish factual corroboration from perspective or opinion.
4. Reject one-sided verified-story promotion on disputed topics when materially distinct sides are missing.
5. Allow attributed opinion to appear when clearly labeled, without counting it as factual corroboration.

## Current Gap Summary

The repo already has reusable infrastructure for crawling, clustering, runtime control, entity storage, transparency, and DuckDuckGo integration inside the fact-checker service. What it does not yet have is:

- explicit BBC-seed plus DDG Lane 1 orchestration
- normalized statement and quote storage
- structured entity-to-speech linkage
- hybrid balance enforcement over attributed speech
- delayed Lane 2 activation based on backlog drain

## Workstreams

1. Lane 1 orchestration
   BBC seed crawl for 10 new articles plus DuckDuckGo expansion up to 5 related articles per seed.

2. Traceability schema
   Normalized statements, quotes, provenance, and balance tables linked to entities, articles, and living stories.

3. Analyst extraction pipeline
   Structured extraction of statements, quotes, speakers, attribution spans, uncertainty, and opinion labels.

4. Governance and publication quality
   Hybrid balance gate, opinion labeling, critic enforcement, and structured synthesis inputs.

5. Lane 2 refinement
   Retain the current fallback intent but delay activation until active work drains and budgets permit.

## Phase Plan

### Phase A: Schema and Contracts

1. Add a new migration after the existing KG and entity migration pattern.
2. Extend the database utility layer so statements and quotes are first-class records.
3. Add typed analyst schemas for attributed speech and balance assessment.

### Phase B: Lane 1 Orchestration

1. Introduce an explicit Lane 1 workflow module.
2. Reuse BBC extraction as the authoritative seed path.
3. Add a reusable DuckDuckGo search adapter for seed expansion.
4. Persist seed-to-result provenance and limits.

### Phase C: Attribution Extraction and Persistence

1. Evolve claim extraction into statement and quote extraction.
2. Persist attributed speech during analysis-report generation.
3. Resolve speaker entities where possible and preserve ambiguity where not.
4. Label opinion, commentary, anonymous-source claims, and factual assertions distinctly.

### Phase D: Synthesis, Critic, and Publication Gating

1. Replace prompt-only quote pulling with structured speech inputs.
2. Strengthen critic checks around attribution completeness and perspective diversity.
3. Add hybrid balance policy and story-level metadata in orchestrator policies.
4. Expose tuning and rollback controls via runtime config.

### Phase E: Lane 2, Transparency, Tests, and Ops Docs

1. Refine Lane 2 activation using backlog-drain signals.
2. Extend transparency repository and publication views.
3. Add focused tests around retrieval, extraction, balance, and fallback behavior.
4. Keep this document as the canonical implementation tracking reference.

## File-by-File Backlog

### Schema and Persistence

#### /app/database/migrations/0XX_add_statement_quote_attribution_tables.sql

Purpose:

- Create normalized tables for `statements`, `quotes`, `statement_entities`, `quote_entities`, and `story_balance_assessments`.
- Optionally create `seed_expansion_runs` and `seed_expansion_results` if seed-provenance storage should remain relational rather than nested metadata.
- Preserve provenance fields including `article_id`, `source_url`, `source_domain`, `speaker_entity_id`, `attribution_text`, source spans, extraction method, confidence, and timestamps.
- Store perspective fields including `perspective_label`, `is_opinion`, and `counts_as_factual_corroboration`.

Dependencies:

- Follow the pattern established in `/app/database/migrations/008_add_kg_audit_and_entity_columns.sql`.

#### /app/database/utils/migrated_database_utils.py

Purpose:

- Add first-class helpers for statement and quote persistence and retrieval.
- Add explicit linking helpers for entities to statements and quotes.
- Extend KG-style audit logging or add equivalent traceability logging.

Recommended additions:

- `add_statement(...)`
- `add_quote(...)`
- `link_statement_to_entity(...)`
- `link_quote_to_entity(...)`
- `get_article_statements(article_id)`
- `get_article_quotes(article_id)`
- `get_entity_statements(entity_id)`
- `get_entity_quotes(entity_id)`

### Analyst Contracts and Extraction

#### /app/agents/analyst/schemas.py

Purpose:

- Add typed models for `AttributedStatement`, `AttributedQuote`, `AttributionSpan`, and `BalanceAssessment`.
- Extend `PerArticleAnalysis` with `statements`, `quotes`, and `attribution_coverage`.
- Extend `AnalysisReport` with aggregate attributed-speech and balance fields.

#### /app/agents/analyst/claims.py

Purpose:

- Evolve current claim extraction into attributed statement extraction.
- Detect direct quotes, paraphrased statements, attribution phrases, uncertainty markers, and extraction spans.
- Produce output that downstream persistence can store without re-parsing free text.

#### /app/agents/analyst/analyst_engine.py

Purpose:

- Add extraction entry points for statements, quotes, and attributed speech.
- Persist extracted speech during `generate_analysis_report(...)`.
- Link extracted speech to resolved entities and preserve unresolved cases explicitly.

Possible organization:

- keep the logic in `analyst_engine.py`, or
- split classification and attribution rules into a new `agents/analyst/attribution.py` helper if the module grows too large.

### Lane 1 Orchestration

#### /app/agents/workflow_orchestrator/lane1_workflow.py

Purpose:

- Introduce an explicit workflow for BBC-first seed retrieval and DuckDuckGo expansion.
- Stop after 10 newly ingested BBC seed articles.
- Build open-web search queries per seed article.
- Cap follow-up retrieval at 5 results per seed.
- Emit normalized seed groups ready for analysis and synthesis.

Alternative location:

- `/app/agents/lane1_orchestrator/workflow.py` if a separate package boundary is preferred.

#### /app/agents/sites/generic_site_crawler.py

Purpose:

- Keep using the current BBC extraction path.
- Mark seed articles with explicit metadata such as `lane1_seed=true` and seed-source provenance.

#### /app/agents/crawler/crawl4ai_adapter.py

Purpose:

- Reuse queue-based fetch mechanics for candidate URLs returned by DuckDuckGo.
- Ensure follow-up articles retain enough metadata to link back to the originating seed article.

#### /app/agents/common/ddg_search_adapter.py or /app/common/ddg_search_service.py

Purpose:

- Extract DuckDuckGo integration into a reusable service rather than coupling Lane 1 to fact-checker internals.
- Build seed queries from article title, entities, and claims.
- Filter obvious junk, ads, or duplicate domains where needed.
- Preserve query provenance for audit and debugging.

Reference:

- `/app/mcp_fact_checker_server/app/service.py`

### Runtime Controls and Source Config

#### /app/agents/workflow_orchestrator/runtime_config.py

Purpose:

- Add rollback-safe controls for Lane 1 and governance behavior.

Recommended keys:

- `orchestrator.lane1.seed_count`
- `orchestrator.lane1.max_related_per_seed`
- `orchestrator.lane1.ddg_enabled`
- `orchestrator.lane1.ddg_max_queries_per_seed`
- `orchestrator.lane1.require_bbc_first`
- `orchestrator.balance_policy.enabled`
- `orchestrator.balance_policy.disputed_topics_hard_gate`
- `orchestrator.balance_policy.min_distinct_sides`
- `orchestrator.balance_policy.allow_opinion_as_perspective`
- `orchestrator.balance_policy.allow_opinion_as_factual_corroboration=false`

#### /app/config/lane1_sources_seed_phase.json

Purpose:

- Clarify BBC as the operational seed source.
- Keep seed configuration authoritative without constraining comparative discovery to a fixed source list.

#### /app/config/lane2_sources_seed_phase.json

Purpose:

- Keep broader-source fallback configuration here.
- Tune per-site budgets and delayed-activation behavior.

### Governance, Synthesis, and Critic Enforcement

#### /app/agents/synthesizer/model_adapter.py

Purpose:

- Replace prompt-only quote pulling with structured attributed-speech inputs.
- Preserve source IDs and attribution trace in synthesis outputs.
- Distinguish corroborated factual support from labeled perspective content.

#### /app/agents/reasoning/tools.py

Purpose:

- Add contradiction and perspective-coverage reasoning over attributed statements.
- Build a side-aware summary that can be consumed before synthesis.

#### /app/agents/critic/tools.py

Purpose:

- Replace or augment current heuristics with checks for attribution completeness, perspective diversity, one-sided sourcing, anonymous-source overuse, and misuse of opinion as factual support.
- Emit structured findings and a story-level balance score or gate decision.

#### /app/agents/workflow_orchestrator/policies.py

Purpose:

- Preserve current publication-lane routing.
- Add explicit acquisition-lane semantics and a hybrid balance gate for disputed topics.
- Store balance metadata in story and publication metadata.

### Lane 2 Refinement and Transparency

#### /app/agents/crawler/crawler_engine.py

Purpose:

- Keep the current zero-ingest trigger behavior where useful.
- Add backlog-drain checks before broad fallback activation.
- Optionally add cooldown or backoff controls.

#### /app/agents/workflow_orchestrator/engine.py

Purpose:

- Expose queue depth or backlog-drain signals the crawler can use for Lane 2 gating.
- Reuse current batching and backpressure controls.

#### /app/agents/dashboard/transparency_repository.py

Purpose:

- Expose attributed statements, quotes, linked entities, and balance assessments for article, cluster, and evidence payloads.
- Make every published story auditable back to sourced statements.

#### /app/justnews_publisher/news/views.py

Purpose:

- Surface structured balance and attribution summaries downstream.
- Distinguish labeled perspectives from corroborated factual claims.

#### /app/docs/feat_article_creation.md

Purpose:

- Update feature-level assumptions where article creation now depends on structured traceability payloads.

## Test Plan

Suggested targets:

- `/app/tests/agents/test_lane1_workflow.py`
- `/app/tests/agents/test_statement_quote_extraction.py`
- `/app/tests/agents/test_balance_policy.py`
- `/app/tests/agents/test_transparency_traceability.py`
- extend `/app/tests/agents/test_crawler_engine.py`
- extend `/app/tests/unit/test_workflow_orchestrator_lane_metadata.py`

Minimum coverage:

1. 10 BBC seeds collected as new articles.
2. DuckDuckGo search invoked per seed article.
3. No more than 5 related results persisted per seed.
4. Direct quotes and paraphrased statements extracted with attribution spans.
5. Entity linkage preserved for attributed speech.
6. Opinion is included when attributed and labeled, but does not count as factual corroboration.
7. Disputed-topic verified-story promotion is blocked when materially distinct sides are missing.
8. Lane 2 fallback waits for backlog drain before broader activation.

## Dependencies and Recommended Order

1. Schema migration first.
2. DB helpers and analyst schemas second.
3. DuckDuckGo adapter and Lane 1 orchestration third.
4. Statement and quote extraction fourth.
5. Synthesis, critic, and policy integration fifth.
6. Transparency and publication updates sixth.
7. Tests and docs throughout, with final runbook updates at the end.

## Scope Boundaries

Included:

- explicit BBC-seed Lane 1 workflow
- DuckDuckGo per-seed open-web search
- full entity, statement, and quote traceability
- hybrid balance policy
- opinion labeling with non-corroboration rule
- Lane 2 deferred fallback refinement

Excluded for MVP:

- broad frontend redesign
- automated political ideology inference
- a full source-stance ontology beyond what is needed for balance coverage

## Verification Checklist

1. Confirm current DuckDuckGo integration exists only in the fact-checker service.
2. Confirm the repo has no normalized statement or quote schema yet.
3. Confirm current critic balance logic is still mostly heuristic.
4. Confirm entity helpers and KG audit patterns remain the right extension points.
5. Confirm current operations docs did not previously contain a canonical plan for this target behavior.

## Open Decisions

1. Define a distinct side of debate operationally: source stance, actor position, or issue-framing category.
2. Decide whether anonymous-source statements may appear in synthesis and under what penalty.
3. Decide whether Lane 2 remains a curated fallback or eventually broadens to all active sources.
4. Decide whether statement and quote records should be mirrored into transparency artifacts immediately or via an export step.

## Recommended Next Execution Slice

1. Draft the migration and the DB helper signatures.
2. Add analyst schemas for attributed speech.
3. Extract the DuckDuckGo adapter from the fact-checker service.
4. Implement the first version of the Lane 1 workflow with persisted seed provenance.
5. Add one end-to-end test that proves BBC seed retrieval plus DuckDuckGo expansion works before moving deeper into governance logic.

## Acceptance Checklist

Use this section as the rollout gate tracker.

### Data Layer

- [ ] Migration 020 applies cleanly in dev, staging, and production-like schemas.
- [ ] Statements and quotes are persisted with provenance and confidence fields.
- [ ] Statement and quote rows can be linked to one or more entities.
- [ ] Story-level balance assessment rows are writable and queryable.

### Lane 1 Retrieval

- [ ] Lane 1 can select BBC seeds and cap at configured seed count.
- [ ] DuckDuckGo expansion runs per seed with query provenance.
- [ ] Related result cap per seed is enforced.
- [ ] Candidate URLs preserve seed linkage metadata through ingestion.

### Governance

- [ ] Hybrid balance policy supports disputed-topic hard gates.
- [ ] Opinion remains allowed when attributed and labeled.
- [ ] Opinion never counts as factual corroboration when policy says false.
- [ ] Critic output includes structured findings for one-sided coverage.

### Transparency and Publication

- [ ] Published payloads expose who said what and where the statement came from.
- [ ] Perspective coverage and missing-side diagnostics are visible in transparency data.
- [ ] Publication metadata includes policy version and balance decision context.

### Operations and Runtime Control

- [ ] Runtime keys for Lane 1 and balance policy validate and apply hot.
- [ ] Rollback path for runtime keys is documented and tested.
- [ ] Monitoring includes at least one signal for balance-gate failure volume.

### Test Gates

- [ ] Unit tests pass for schema serialization and traceability helper methods.
- [ ] Unit tests pass for DDG service and Lane 1 planning behavior.
- [ ] Integration test proves end-to-end seed-to-related trace persistence.
- [ ] Regression test proves Lane 2 remains delayed until backlog-drain conditions are met.