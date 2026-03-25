# Crawl4AI Prioritized Improvement Roadmap (JustNews)

Date: 2026-03-24
Scope: Unified crawl and crawler scripts, with priority on ingestion yield, reliability, and editorial throughput.

## Objectives

1. Increase crawl throughput and freshness without raising failure rates.
2. Prevent silent pipeline degradation when dependencies are unavailable.
3. Improve extraction precision for high-value publishers.
4. Close observability gaps for Lane 1 and Lane 2 operations.
5. Use `sources` table intelligence to improve source selection speed/quality without schema bloat.

## Sources Table Alignment (Lean, High-Impact)

### Current useful per-site state already in `sources`
- Identity and routing:
  - `domain`, `url`, `name`, `country`, `language`
- Crawl recency and trust/lifecycle:
  - `last_crawl_at`, `last_verified`, `source_state`, `source_state_reason`, `source_state_updated_at`
- Avoidance controls:
  - `paywall`, `paywall_type`
- Flexible extension:
  - `metadata` JSON (already used for `paywall_detection` and strategy hints)

### Useful Crawl4AI-observable signals (candidate set)
- Run outcome signals:
  - crawl success/failure, no-candidate, stalled, blocked, paywall-dominated
- Access/friction signals:
  - latest HTTP status class, robots disallow, repeated anti-bot blocks
- Throughput/quality signals:
  - candidates produced, ingested count, duplicate pressure, short-term yield trend
- Adaptive behavior signals:
  - stop reason and confidence summaries

### Persist where (to avoid bloat)
- Keep compact source selection state in `sources` (small, decision-oriented, current snapshot).
- Keep per-run time series in `crawler_performance` (or dedicated event tables), not in `sources`.
- Keep high-cardinality payloads out of MariaDB source rows.

### Proposed minimal new `sources` fields (only if they improve scheduling/routing)
- `last_crawl_outcome` (VARCHAR/ENUM-like): `success`, `no_candidates`, `blocked`, `paywalled`, `error`
- `last_candidate_count` (INT): latest candidate pressure for quick source ranking
- `crawl_fail_streak` (SMALLINT): consecutive failures for source-level suppression
- `crawl_blocked_until` (DATETIME): temporary skip window for blocked/failing domains
- `crawl_quality_score` (DECIMAL): compact rolling score for source prioritization

### Data explicitly excluded from `sources` (bloat guardrail)
- Raw HTML/cleaned HTML/markdown bodies
- Full extracted link lists or per-page candidate lists
- Screenshots/PDF/MHTML blobs
- Per-page adaptive coverage internals and verbose debugging traces
- Large nested run histories in `metadata`

### Keep `metadata` bounded
- Restrict to compact JSON keys used for decisions (for example paywall counters, strategy hints, last_reason_code).
- Cap key count and value size; move detailed history to time-series/event tables.

## P1: Immediate / Highest Impact

### P1.1 Add multi-URL crawling with dispatcher control
- Change:
  - Add `arun_many` path for profile batches in Crawl4AI adapter.
  - Use `MemoryAdaptiveDispatcher` with controlled session permits.
- Why this matters:
  - Improves throughput and reduces per-site serial bottlenecks.
  - Better memory safety under larger domain sets.
- Primary files:
  - `agents/crawler/crawl4ai_adapter.py`
  - `agents/crawler/crawler_engine.py`
- KPIs:
  - At least 2x URLs/minute vs current baseline.
  - No regression in crawl success rate.

### P1.2 Add preflight dependency gating before unified crawl
- Change:
  - Add explicit preflight checks for required downstreams (HITL, persistence dependencies).
  - Return explicit degraded/fail-fast status if required services are unavailable.
- Why this matters:
  - Prevents silent candidate drops and misleading successful run outcomes.
- Primary files:
  - `agents/crawler/crawler_engine.py`
  - `agents/crawler/main.py`
- KPIs:
  - 0 silent handoff failures.
  - 100% of dependency outages produce explicit degraded/error run status.

### P1.3 Expand Crawl4AI run-config forwarding for high-value options
- Change:
  - Add support for: `session_id`, `css_selector`, `extraction_strategy`, `check_robots_txt`, `page_timeout`, `stream`, `js_only`.
- Why this matters:
  - Enables domain-specific control and better crawl behavior on dynamic/complex sites.
- Primary files:
  - `agents/crawler/crawl4ai_adapter.py`
  - `agents/crawler_control/crawl_profiles.py`
- KPIs:
  - Reduced `no_new_candidates` rate on priority domains.

### P1.4 Add source-level crawl outcome intelligence (lean schema + scheduler use)
- Change:
  - Add the minimal `sources` fields listed in the alignment section.
  - Update source selection logic to use fail streak, blocked-until, and quality score.
- Why this matters:
  - Directly improves crawl speed by avoiding repeatedly failing domains.
  - Improves quality by prioritizing historically productive sources.
- Primary files:
  - `database/migrations/*`
  - `agents/crawler/crawler_utils.py`
  - `agents/crawler/crawler_engine.py`
- KPIs:
  - Lower blocked/error retry waste per run.
  - Higher ingest yield per attempted source.

## P2: Near-Term / High Value

### P2.1 Add structured extraction strategies on priority domains
- Change:
  - Introduce `JsonCssExtractionStrategy` profiles for top publishers with stable DOM patterns.
- Why this matters:
  - Improves extraction precision and reduces downstream ambiguity.
- Primary files:
  - `config/crawl_profiles.yaml`
  - `agents/crawler/crawl4ai_adapter.py`
- KPIs:
  - +20% to +30% valid extraction precision for configured domains.

### P2.2 Add lane-aware fallback telemetry contract
- Change:
  - Emit `lane2_fallback` summary object with trigger reason, attempted domains, outcomes, and block causes.
- Why this matters:
  - Faster diagnosis and safer lane policy tuning.
- Primary files:
  - `agents/crawler/crawler_engine.py`
- KPIs:
  - 100% of fallback runs include complete lane2 telemetry payload.

### P2.3 Enforce complete per-site detail accounting
- Change:
  - Ensure every attempted site has a detail row, including zero-candidate and skipped paths.
- Why this matters:
  - Eliminates observability blind spots during operations triage.
- Primary files:
  - `agents/crawler/crawler_engine.py`
- KPIs:
  - `site_ingestion_details_count == attempted_sites` for all runs.

### P2.4 Add sources-vs-Crawl4AI data contract tests
- Change:
  - Add tests that enforce what may be written to `sources` versus time-series tables.
  - Add schema guardrails to prevent large payloads from being persisted in `sources.metadata`.
- Why this matters:
  - Prevents long-term table bloat and protects query performance.
- Primary files:
  - `tests/agents/crawler/`
  - `agents/crawler/crawler_utils.py`
  - `database/migrations/*`
- KPIs:
  - Zero regressions that add high-cardinality blobs to `sources`.

## P3: Mid-Term / Optimization

### P3.1 Dynamic-site reliability hooks
- Change:
  - Add Crawl4AI hook-driven workflows for JS-heavy pages and paginated experiences.
- Why this matters:
  - Better reliability for dynamic content capture.
- Primary files:
  - `agents/crawler/crawl4ai_adapter.py`
  - `config/crawl_profiles.yaml`

### P3.2 Domain-specific anti-block policy
- Change:
  - Add per-domain retry/header/proxy strategy with explicit block classification.
- Why this matters:
  - Reduces 401/403-driven stalls and adaptive thrashing.
- Primary files:
  - `agents/crawler/crawler_engine.py`
  - `agents/crawler/enhancements/*`

### P3.3 Automated lane-behavior acceptance validator
- Change:
  - Add post-run validator for lane execution, dependency health, and detail completeness.
- Why this matters:
  - Early regression detection and safer rollout.
- Primary files:
  - `scripts/ops/`
  - `tests/agents/crawler/`

## Recommended Implementation Order

1. P1.1 multi-URL + dispatcher
2. P1.2 preflight dependency gating
3. P1.3 run-config expansion
4. P1.4 source-level crawl outcome intelligence (lean schema)
5. P2.1 structured extraction for priority domains
6. P2.2 lane2 telemetry contract
7. P2.3 complete per-site detail accounting
8. P2.4 sources-vs-Crawl4AI contract tests
9. P3 items

## Delivery Plan and Exit Criteria

### Sprint A (P1)
- Deliverables:
  - `arun_many` path behind profile flag
  - dependency preflight gating
  - expanded run-config support
  - minimal source-outcome fields and scheduler integration
- Exit criteria:
  - Throughput increase validated
  - no silent handoff failures
  - no reliability regression
  - measurable reduction in retries against blocked/failing sources

### Sprint B (P2)
- Deliverables:
  - structured extraction profiles for top domains
  - lane2 telemetry object in summary
  - complete per-site detail accounting
  - sources-vs-Crawl4AI persistence contract tests
- Exit criteria:
  - extraction precision improvements measured
  - fallback observability complete
  - no source-table bloat regressions

### Sprint C (P3)
- Deliverables:
  - dynamic-site hooks
  - anti-block policy
  - acceptance validator automation
- Exit criteria:
  - improved dynamic-site success rates
  - fewer blocked-domain stalls
  - validator catches regressions in CI/scheduled runs

## Execution Tracker

- [x] P1.1 Multi-URL + dispatcher
- [x] P1.2 Preflight dependency gating
- [x] P1.3 Run-config expansion
- [x] P1.4 Source-level crawl outcome intelligence (lean schema)
- [x] P2.1 Structured extraction for priority domains
- [x] P2.2 Lane2 telemetry contract
- [x] P2.3 Complete per-site detail accounting
- [x] P2.4 Sources-vs-Crawl4AI contract tests
- [x] P3.1 Dynamic-site reliability hooks
- [x] P3.2 Domain-specific anti-block policy
- [x] P3.3 Lane-behavior acceptance validator

## Notes

- This roadmap is intended as the canonical implementation reference.
- Update this file as each milestone is delivered (dates, PR links, measured KPI deltas).
- Implemented in this cycle:
  - Crawl4AI batch seed crawling (`arun_many`) with optional dispatcher initialization from profile.
  - Strict/soft preflight contract in unified crawl summary (`preflight`).
  - Lane 2 fallback summary contract (`lane2_fallback`) with attempted domains and counts.
  - Per-site detail fallback rows when no candidate details were emitted.
  - Lean `sources` intelligence migration and write path for crawl outcomes.
  - Structured extraction strategy support (`JsonCssExtractionStrategy`) for profile-driven domains.
  - Dynamic-site JS hook support (`pre_nav_js`/`post_nav_js`) in profile `extra`.
  - Blocked-domain outcome classification and source cooldown persistence.
  - Source persistence contract tests enforcing lean-field writes.
  - Post-run contract validator script: `scripts/ops/validate_crawl_lane_behavior.py`.
