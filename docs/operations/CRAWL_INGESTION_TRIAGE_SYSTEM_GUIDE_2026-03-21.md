# Crawl Ingestion Triage System Guide

Date: 2026-03-21
Status: Active (feature-flagged)
Audience: Operators, developers, on-call responders

## Purpose

The crawl ingestion triage system prevents low-value pages from entering expensive downstream pipeline stages (analysis, fact-checking, synthesis).

Primary goals:
1. Reject obvious non-news pages early.
2. Reduce wasted compute in bottleneck stages.
3. Preserve useful ambiguous content using selective AI classification.
4. Record reason-coded decisions for audit and tuning.

## Scope and Boundaries

Current implementation applies to Crawl4AI-backed crawl candidates produced in:
1. [agents/crawler/crawl4ai_adapter.py](agents/crawler/crawl4ai_adapter.py)

Downstream skip accounting and reason logging is handled in:
1. [agents/crawler/crawler_engine.py](agents/crawler/crawler_engine.py)

Related decision log for this rollout:
1. [docs/operations/CRAWL_INGESTION_TRIAGE_DECISIONS_2026-03-21.md](docs/operations/CRAWL_INGESTION_TRIAGE_DECISIONS_2026-03-21.md)

## System Architecture

The system is layered:

1. Deterministic heuristic gate (fast)
- Evaluates URL path and content shape.
- Produces accept, reject, or ambiguous.

2. Optional AI gate (selective)
- Invoked for ambiguous pages by default.
- Returns accept, reject, or quarantine with confidence and reason codes.
- Uses dedicated `TriageAdapter` model-store resolution (adapter-specific routing).

3. Confidence policy
- AI reject/quarantine is enforced only above threshold.
- Otherwise heuristic outcome remains in effect.

4. Skip propagation
- Rejected/quarantined candidates are marked skip_ingest.
- Engine records status and reason details in per-site crawl details.

## Decision Flow

For each candidate article:

1. Build article candidate from Crawl4AI extraction.
2. If triage feature flag is off:
- Ingest path is unchanged.
3. If triage is on:
- Run heuristic triage.
4. If AI triage is enabled and policy permits:
- Optionally run AI triage (ambiguous-only by default).
5. Resolve final decision with confidence gate.
6. If final decision is reject or quarantine:
- Set skip_ingest = true.
- Set ingestion_status = triage_rejected or triage_quarantined.
- Set skip_reason = ingestion_triage.
- Attach reason-coded metadata.
7. Engine filters skip-marked candidates before ingest and records skip detail.

## Heuristic Functionality

Heuristic checks currently include:

1. Utility/non-news URL detection
- contact, about, mission, corporate, careers, support and similar routes.

2. Index/navigation URL detection
- category/tag/topic/section/latest/most-read/opinion and similar routes.

3. Overlay-heavy content signals
- cookie/consent/privacy and related text patterns.

4. Navigation-heavy text signals
- editors picks, most read, top stories, newsletter, ad-like markers.

5. Narrative length check
- very short content is down-ranked/rejected in low-density contexts.

Heuristic outcomes:
1. accept
2. reject
3. ambiguous

## AI Triage Functionality

AI triage behavior:

1. Uses dedicated adapter implementation in `agents/common/triage_adapter.py`.
2. Prompt asks for strict JSON with keys:
- decision
- confidence
- page_type
- reason_codes

3. Accepts only decisions in:
- accept
- reject
- quarantine

4. Resolves model-store adapter metadata and passes adapter headers to vLLM.
5. Parses JSON output defensively.
6. If AI call fails, times out, or returns invalid payload:
- Falls back to heuristic decision.

Model-store defaults for triage adapter:
1. Agent: `crawler_triage`
2. Adapter name: `qwen2_crawler_triage_v1`
3. Mapping files:
- `AGENT_MODEL_MAP.json`
- `AGENT_MODEL_RECOMMENDED.json`

## Confidence and Override Policy

Current policy:

1. AI accept can upgrade ambiguous heuristic outcomes.
2. AI reject/quarantine is enforced only when confidence meets threshold.
3. Reject threshold supports domain-specific overrides with global fallback.
4. Low-confidence AI reject/quarantine does not override heuristic accept.
5. If heuristic is deterministic reject, reject remains unless policy is changed.

This policy intentionally favors high precision for hard rejects to avoid false negatives on real news pages.

## Metadata Contract

Triage metadata is attached to each triaged candidate under:

1. extraction_metadata.ingestion_triage

Fields:
1. enabled
2. decision
3. confidence
4. reason_codes
5. source (heuristic or ai)
6. page_type
7. domain
8. profile_slug

If rejected/quarantined, additional top-level fields are set:
1. skip_ingest
2. ingestion_status = triage_rejected or triage_quarantined
3. skip_reason = ingestion_triage
4. triage_reason (compact reason summary)

## Engine Interaction

Crawler engine behavior was generalized from paywall-only skip handling to reason-aware skip handling:

1. Skip-marked candidates are removed before ingest.
2. Skip details are appended to site detail records.
3. Paywall accounting remains intact for paywall-specific skips.
4. Triage skips preserve reason context for diagnostics and reporting.
5. Quarantined triage candidates can be persisted to a local review queue when enabled.

Training-system feedback integration:
1. Triage decisions can be forwarded as prediction feedback via `training_system.core.system_manager.collect_prediction`.
2. Training channel defaults to agent `crawler_triage` and task `ingestion_triage`.
3. Forwarding is sampled and feature-flagged to control load.
4. Crawler exposes `update_triage_adapter` to receive aggregated examples from training coordinator.

Code location:
1. [agents/crawler/crawler_engine.py](agents/crawler/crawler_engine.py)

## User Interaction Model

There is no interactive UI yet; interaction is operational and configuration-driven.

### Operators (runtime control)

Operators control triage using environment flags.

Core flags:
1. CRAWL4AI_INGESTION_TRIAGE_ENABLED
2. CRAWL4AI_AI_TRIAGE_ENABLED
3. CRAWL4AI_AI_TRIAGE_AMBIGUOUS_ONLY
4. CRAWL4AI_AI_TRIAGE_REJECT_CONFIDENCE
5. CRAWL4AI_AI_TRIAGE_DOMAIN_THRESHOLDS_JSON
6. CRAWL4AI_AI_TRIAGE_TIMEOUT_SEC
7. CRAWL4AI_TRIAGE_ADAPTER_NAME
8. CRAWL4AI_TRIAGE_MODEL
9. CRAWL4AI_TRIAGE_TRAINING_FEEDBACK_ENABLED
10. CRAWL4AI_TRIAGE_TRAINING_SAMPLE_RATE
11. CRAWL4AI_TRIAGE_TRAINING_AGENT
12. UNIFIED_CRAWLER_TRIAGE_QUARANTINE_ENABLED
13. UNIFIED_CRAWLER_TRIAGE_QUARANTINE_DIR
14. UNIFIED_CRAWLER_TRIAGE_QUARANTINE_MAX_ITEMS

AI endpoint settings reused from model runtime:
1. VLLM_BASE_URL
2. VLLM_MODEL
3. VLLM_API_KEY

Operator workflow:
1. Enable deterministic triage first.
2. Observe skip reasons and ingest throughput.
3. Enable AI triage on ambiguous pages.
4. Tune reject confidence threshold conservatively.
5. Optionally apply stricter domain-specific thresholds for noisy sources.
6. Enable quarantine queue persistence for reviewer feedback loops.
7. Enable sampled training-feedback forwarding for triage adapter improvement.
5. Compare downstream analysis/fact-check load and publication quality.

### Developers (integration and debugging)

Developer interaction points:
1. Candidate metadata inspection in article payloads.
2. Site detail skip records in crawl summaries.
3. Unit tests for heuristic and AI-override behavior.

Tests:
1. [tests/agents/crawler/test_crawl4ai_ingestion_triage.py](tests/agents/crawler/test_crawl4ai_ingestion_triage.py)
2. [tests/agents/crawler/test_crawl4ai_follow_external.py](tests/agents/crawler/test_crawl4ai_follow_external.py)

## Operational Modes

Recommended rollout sequence:

1. Mode A: triage off
- Baseline behavior.

2. Mode B: heuristic only
- Enable CRAWL4AI_INGESTION_TRIAGE_ENABLED.
- Keep AI triage disabled.

3. Mode C: heuristic + AI for ambiguous pages
- Enable CRAWL4AI_AI_TRIAGE_ENABLED.
- Keep ambiguous-only mode enabled.

4. Mode D: tune confidence threshold
- Increase or decrease reject threshold based on observed false-positive/false-negative patterns.

5. Mode E: domain-tuned rollout
- Add domain-specific threshold overrides for problematic domains while keeping global defaults stable.

6. Mode F: quarantine queue enabled
- Persist quarantined candidates for deferred review and rule tuning.

## Example Configuration

Heuristic-only:

1. CRAWL4AI_INGESTION_TRIAGE_ENABLED=true
2. CRAWL4AI_AI_TRIAGE_ENABLED=false

Heuristic + AI on ambiguous:

1. CRAWL4AI_INGESTION_TRIAGE_ENABLED=true
2. CRAWL4AI_AI_TRIAGE_ENABLED=true
3. CRAWL4AI_AI_TRIAGE_AMBIGUOUS_ONLY=true
4. CRAWL4AI_AI_TRIAGE_REJECT_CONFIDENCE=0.78
5. CRAWL4AI_AI_TRIAGE_TIMEOUT_SEC=8

Heuristic + AI with domain overrides:

1. CRAWL4AI_INGESTION_TRIAGE_ENABLED=true
2. CRAWL4AI_AI_TRIAGE_ENABLED=true
3. CRAWL4AI_AI_TRIAGE_AMBIGUOUS_ONLY=true
4. CRAWL4AI_AI_TRIAGE_REJECT_CONFIDENCE=0.78
5. CRAWL4AI_AI_TRIAGE_DOMAIN_THRESHOLDS_JSON={"example.com":0.90,"newswire.local":0.85}

Quarantine queue enabled:

1. UNIFIED_CRAWLER_TRIAGE_QUARANTINE_ENABLED=true
2. UNIFIED_CRAWLER_TRIAGE_QUARANTINE_DIR=/tmp/justnews_triage_quarantine
3. UNIFIED_CRAWLER_TRIAGE_QUARANTINE_MAX_ITEMS=1000

Adapter training feedback enabled:

1. CRAWL4AI_TRIAGE_TRAINING_FEEDBACK_ENABLED=true
2. CRAWL4AI_TRIAGE_TRAINING_SAMPLE_RATE=0.25
3. CRAWL4AI_TRIAGE_TRAINING_AGENT=crawler_triage

## Failure Modes and Safeguards

1. AI endpoint unavailable
- Behavior: fallback to heuristic outcome.
- Impact: reduced semantic discrimination, no hard failure.

2. AI malformed output
- Behavior: ignored, fallback to heuristic.

3. Over-rejection risk
- Safeguard: confidence threshold, domain overrides, and ambiguous-only AI mode.

4. Under-rejection risk
- Mitigation: expand deterministic reason patterns and tune threshold.

5. Performance concerns
- Mitigation: AI call is selective and bounded by timeout.

## Observability and Auditability

Current audit signal sources:
1. Candidate-level ingestion_triage metadata.
2. Site detail records in crawl summary for skipped candidates.
3. Triage metrics for decisions, sources, reasons, and confidence.
4. Quarantine queue files when persistence is enabled.
5. Optional training-forward prediction events in training system metrics.

Recommended next observability additions:
1. Dashboard panel for triage decision counts by source and reason code.
2. Trend view for skip rates by source domain.
3. Correlation with downstream fact-check queue depth and latency.
4. Alerting on sudden spikes in triage_quarantined rates.

## Current Limitations

1. Quarantine is persisted for offline review, but no first-class review UI/workflow exists yet.
2. Domain-specific threshold overrides are static env config (no dynamic control plane yet).
3. Broader non-Crawl4AI paths are not yet triaged by this mechanism.
4. Dashboard-level triage KPIs are not yet fully wired.
5. Adapter training examples are persisted for offline/async training; no in-process fine-tune executor is embedded in crawler runtime.

## Extension Roadmap

1. Add review workflow and adjudication lifecycle on top of quarantine queue artifacts.
2. Add dynamic per-domain policy management via runtime config API.
3. Add metrics and Grafana panels for triage decision quality.
4. Expand triage coverage to additional crawl ingestion paths.
5. Add automated A/B harness for triage mode comparisons.
6. Add scheduled promotion flow from persisted triage datasets to model-store adapter versions.

## Verification Commands

Run targeted tests:

1. /app/.venv/bin/pytest -q tests/agents/crawler/test_crawl4ai_ingestion_triage.py tests/agents/crawler/test_crawl4ai_follow_external.py tests/common/test_triage_adapter_model_store.py

Run full crawler test subset (optional):

1. /app/.venv/bin/pytest -q tests/agents/crawler

## Summary

The triage system is a shift-left quality control layer that reduces ingestion of non-news and navigation-heavy pages before expensive downstream processing. It combines deterministic speed with optional AI judgment for ambiguous pages and preserves reason-coded decision telemetry for continuous tuning.
