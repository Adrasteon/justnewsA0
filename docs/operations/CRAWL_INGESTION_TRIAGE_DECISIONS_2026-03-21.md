# Crawl Ingestion Triage Decisions

Date: 2026-03-21
Status: Implemented first-pass triage path

Detailed reference:
1. [Crawl Ingestion Triage System Guide](./CRAWL_INGESTION_TRIAGE_SYSTEM_GUIDE_2026-03-21.md)

## Scope

This document captures:
1. Prompt experiment outcomes
2. Discussion conclusions and decisions
3. Recommended triage method
4. Initial implementation details and flags
5. Adapter and training-system integration updates

## What We Tested

1. Reproducible prompt experiments on fixed cluster snapshots across baseline and strict variants.
2. Progressive cluster filtering (`filtered`, `filtered_v2`, `filtered_v3`) to remove contaminated inputs.
3. Prompt hardening (`v3b`) to reduce short-body strict outputs.
4. Dual-dimension evaluation:
Format compliance and utility value.

Experiment artifacts referenced:
1. `test_prompt_experiments/run_20260321T173048Z_filtered_v2`
2. `test_prompt_experiments/run_20260321T180600Z_filtered_v3`
3. `test_prompt_experiments/run_20260321T181500Z_filtered_v3b`

## Key Findings

1. Input contamination is a primary quality bottleneck.
2. Contamination patterns observed:
modal overlays, index/navigation pages, and non-news utility pages.
3. Late-pipeline rejection is costly because analysis and fact-checking are bottlenecks.
4. Some outputs marked unstructured were still utility-rich (key points, cautions, quotes).
5. Prompt hardening helped strict variants, but ingestion quality remained the dominant lever.

## Decisions

1. Shift quality control earlier to ingestion.
2. Keep downstream hardening, but treat it as second-line defense.
3. Use layered triage:
fast deterministic gates first, optional AI classification for ambiguous cases.
4. Track both format quality and utility quality in evaluation.
5. Preserve reason-coded telemetry for all skipped candidates.

## Recommended Triage Method

1. Deterministic stage (cheap and fast):
URL and text-shape checks for non-news utilities, index/navigation pages, overlay-heavy content, and very short pages.
2. AI stage (selective):
Only classify ambiguous pages by default.
3. Decision policy:
`accept`, `reject`, or `quarantine` with confidence and reason codes.
4. Confidence gate:
AI reject/quarantine enforced only above threshold; otherwise fallback keeps candidate.
5. Fail-safe:
If AI triage fails or times out, keep deterministic result and continue.

## Initial Implementation

Implemented in:
1. `agents/crawler/crawl4ai_adapter.py`
2. `agents/crawler/crawler_engine.py`

### Adapter behavior

1. Added feature-flagged ingestion triage path for Crawl4AI candidates.
2. Added deterministic heuristic triage decisions.
3. Added dedicated first-class AI triage adapter (`TriageAdapter`) instead of inline HTTP calls.
4. Added metadata payload under `extraction_metadata.ingestion_triage` with:
`decision`, `confidence`, `reason_codes`, `source`, `page_type`.
5. Mark rejected or quarantined candidates with:
`skip_ingest=true`, `ingestion_status` in (`triage_rejected`, `triage_quarantined`), `skip_reason=ingestion_triage`.
6. Added optional triage prediction forwarding into training integration (`collect_prediction`) for adapter training data.

### Model-store and training integration update

1. Added dedicated model-map entries for `crawler_triage` in:
- `AGENT_MODEL_MAP.json`
- `AGENT_MODEL_RECOMMENDED.json`
2. Added new shared adapter implementation:
- `agents/common/triage_adapter.py`
3. Triage adapter resolves its own model-store metadata via `get_agent_model_metadata` and sends:
- `x-justnews-adapter-path`
- `x-justnews-adapter-name`
4. Training system now includes `crawler_triage` as a first-class trainable agent channel:
- training buffer + update routing in `training_system/core/training_coordinator.py`
- agent config in `training_system/core/system_manager.py`
- validator allow-list in `training_system/utils/helpers.py`
5. Implemented crawler MCP training tool endpoint:
- `agents/crawler/main.py` exposes `update_triage_adapter`
- accepted examples are persisted to JSONL for adapter training data collection

### Hardening Update (Same Session)

The following hardening gaps were closed:

1. Quarantine handling:
- `quarantine` now has explicit status `triage_quarantined`.
- Quarantined candidates are persisted to a dedicated quarantine queue on disk.

2. Domain-aware reject thresholds:
- Added per-domain AI reject/quarantine confidence threshold support.
- Global threshold remains default; domain overrides apply by exact or suffix match.

3. Triage metrics:
- Added decision/source/reason/domain metric emission for triage outcomes.

4. Expanded tests:
- Added test coverage for domain threshold behavior and quarantine semantics.

### Engine behavior

1. Generalized skip handling from paywall-only to reason-aware skip candidates.
2. Preserves paywall accounting while recording triage skip reason codes in site details.

## Runtime Flags

1. `CRAWL4AI_INGESTION_TRIAGE_ENABLED` (default `false`)
2. `CRAWL4AI_AI_TRIAGE_ENABLED` (default `false`)
3. `CRAWL4AI_AI_TRIAGE_AMBIGUOUS_ONLY` (default `true`)
4. `CRAWL4AI_AI_TRIAGE_REJECT_CONFIDENCE` (default `0.78`)
5. `CRAWL4AI_AI_TRIAGE_TIMEOUT_SEC` (default `8`)
6. `CRAWL4AI_AI_TRIAGE_DOMAIN_THRESHOLDS_JSON` (default empty)
7. `CRAWL4AI_TRIAGE_ADAPTER_NAME` (default `qwen2_crawler_triage_v1`)
8. `CRAWL4AI_TRIAGE_MODEL` (optional explicit override)
9. `CRAWL4AI_TRIAGE_TRAINING_FEEDBACK_ENABLED` (default `false`)
10. `CRAWL4AI_TRIAGE_TRAINING_SAMPLE_RATE` (default `1.0`)
11. `CRAWL4AI_TRIAGE_TRAINING_AGENT` (default `crawler_triage`)
12. `UNIFIED_CRAWLER_TRIAGE_QUARANTINE_ENABLED` (default `true`)
13. `UNIFIED_CRAWLER_TRIAGE_QUARANTINE_DIR` (default `/tmp/justnews_triage_quarantine`)
14. `UNIFIED_CRAWLER_TRIAGE_QUARANTINE_MAX_ITEMS` (default `5000`)

AI triage uses existing model endpoint variables:
1. `VLLM_BASE_URL`
2. `VLLM_MODEL`
3. `VLLM_API_KEY`

## Validation

Added targeted tests:
1. `tests/agents/crawler/test_crawl4ai_ingestion_triage.py`
2. `tests/common/test_triage_adapter_model_store.py`

Test coverage includes:
1. Utility URL rejection by heuristic gate
2. Article-like accept by heuristic gate
3. Ambiguous-case AI override and metadata/skip behavior
4. Triage training-forward hook behavior
5. Triage adapter model-store header/path resolution and strict-mode enforcement

## Next Steps

1. Add ingestion triage metrics dashboards (accept/reject/quarantine by reason).
2. Run A/B crawl cycle:
deterministic-only vs deterministic+AI-on-ambiguous, then compare downstream load and publication quality.
