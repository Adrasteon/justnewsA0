# JustNews — Project Architecture Overview

This document provides a concise architecture overview for the JustNews project: per-agent responsibilities, functional
intent and completion status, common workflow patterns, and training patterns used by the system. It is intended as a
developer-facing reference to help plan work, reviews, and operational rollouts.

## Executive summary

JustNews is an agent-driven news ingestion and processing platform built around a few core ideas:

- Agent-oriented design: independent agents encapsulate responsibilities (crawler, hitl, memory, archive, fact-checker,
  synthesizer, etc.).

- Crawl4AI-first orchestration for navigation and JS-handling, with a Trafilatura-first extraction pipeline.

- Human-in-the-loop (HITL) staging for labeling, QA and forwarding before ingestion.

- Dual persistence strategy: structured metadata in MariaDB, vector embeddings in Chroma (or similar), and raw HTML
  archived to filesystem storage.

- Observability and evaluation are first-class: adaptive metrics, Prometheus exporters, parity evaluations and
  acceptance runbooks.

Current branch: `dev/crawl_scrape` contains the recent Crawl4AI enforcement docs, evaluation harness, and HITL service
improvements.

## System map (high level)

- Scheduler / Orchestrator

- `scripts/ops/run_crawl_schedule.py` — schedules crawls, expands profiles, emits scheduler metrics.

- Crawler layer

- `agents/crawler/crawler_engine.py` — unified engine. Chooses strategy, submits HITL candidates, ingests articles.

- `agents/crawler/crawl4ai_adapter.py`— translates site profiles to`crawl4ai` objects and runs AdaptiveCrawler or
  AsyncWebCrawler.

- `agents/sites/generic_site_crawler.py` — fallback requests-based crawler.

- `agents/sites/*_crawler.py`— per-site (e.g.,`bbc_crawler.py`) specialized crawlers (some stubs).

- Extraction

- `agents/crawler/extraction.py` — Trafilatura-first extractor with fallbacks to readability, jusText and a plain
  sanitizer.

- HITL service

- `agents/hitl_service/` — FastAPI-based staging service, SQLite staging DB, label lifecycle and forwarding logic.

- Agents Bus & Ingestion

- MCP Bus (`agents/mcp_bus`) — RPC-style bus for agent-to-agent calls
  (e.g.,`memory.ingest_article`,`archive.queue_article`).

- Memory & Archive

- `agents/memory/`— ingestion APIs, embedding store integration. Uses dual-db strategies in`database/`.

- `archive/`and`archive_storage/raw_html/` — raw HTML and archival storage.

- Downstream agents

- `agents/fact_checker`,`agents/chief_editor`,`agents/synthesizer`,`agents/journalist` — higher-level processing, QA,
  and editorial workflows.

- Infrastructure & Observability

- `infrastructure/` contains Prometheus/Grafana templates, systemd scripts, and deployment helpers.

## Model Inference Strategy (GPU Architecture)

JustNews relies on a highly optimized **Single-GPU (24GB VRAM)** architecture designed to balance deep reasoning capabilities with multi-modal support.

### Core Intelligence
- **Primary Model**: `Qwen 2.5 14B Instruct (AWQ/Int4)` served via vLLM.
- **Role**: Handles all text synthesis, fact-checking, editorial review, and reasoning tasks.
- **Performance**: Consumes ~14.7GB VRAM (Weights + Context), leaving ~9GB headroom.

### Multi-modal & On-Demand Support
Due to VRAM constraints, we employ a **load-swap strategy** for specialized models:
- **Vision (Qwen-VL 2B)**: Loaded temporarily for image analysis, then unloaded.
- **Audio (Whisper Large V3)**: Loaded temporarily for transcription, then unloaded.

This strategy ensures that the Primary Model has maximum context window access (up to 32k tokens) during complex reasoning tasks, rather than permanently reserving VRAM for idling operational models.

## Per-agent functional responsibilities and completion status

The table below lists agents, their functional intent, and current level of implementation (Done / Partial / Stub /
Planned).

- Crawler Engine — `agents/crawler/crawler_engine.py` — Done/Partial

- Intent: unify crawling strategies (Crawl4AI adaptive, Crawl4AI run, Generic fallback), submit HITL candidates, call
  ingestion APIs.

- Status: Implemented core paths, HITL submission and ingestion integrated. Improvements on CI and enforcing Crawl4AI
  runtime are pending.

- Crawl4AI Adapter — `agents/crawler/crawl4ai_adapter.py` — Done

- Intent: translate YAML profiles into `BrowserConfig`and`CrawlerRunConfig`, handle adaptive crawls, build article
  dicts.

- Status: Implemented; guarded around optional `crawl4ai` dependency. Emits adaptive metrics.

- Generic Site Crawler — `agents/sites/generic_site_crawler.py` — Done

- Intent: lightweight HTTP fetcher and extraction fallback for sites where Crawl4AI is unavailable or disabled.

- Status: Implemented and used as emergency fallback.

- Site-specific Crawlers — `agents/sites/bbc_crawler.py` — Stub/Deprecated

- Intent: ultra-fast specialized crawlers for priority sites. Historically used for speed but de-prioritised due to
  quality/politeness.

- Status: present as stubs. Recommendation: deprecate and migrate to Crawl4AI profiles.

- Extraction Pipeline — `agents/crawler/extraction.py` — Done

- Intent: Trafilatura-first extraction with fallback to readability, jusText, and plain sanitiser. Archive raw HTML and
  annotate metadata.

- Status: Implemented.

- NewsReader Agent — `agents/newsreader/` — Done

- Intent: Vision-based content extraction using LLaVA. Capable of "reading" screenshots of complex layouts.

- Status: Implemented with Lazy Loading for optimized startup performance.

- HITL Service — `agents/hitl_service/` — Done/Partial

- Intent: staging DB for labels, QA endpoints, forwarding to downstream agents; supports manual review and programmatic
  flows.

- Status: Implemented FastAPI service, DB migrations, QA endpoints; forwarding and ingestion-state handling improved
  recently, but downstream integrations require staging verification.

- Memory Agent — `agents/memory/` — Partial

- Intent: ingest articles, generate embeddings, store structured records in MariaDB and vector DB, provide recall APIs.

- Status: Core ingestion exists; embedding store wiring and operational tuning may be partial depending on environment.

- Archive Agent — `agents/archive/`and`archive_storage/raw_html/` — Partial

- Intent: store raw HTML/artefacts and provide retrieval for auditing and reprocessing.

- Status: MCP tool `queue_article`now normalizes HITL ingest payloads, snapshots raw HTML via`raw_html_*` helpers, and
  writes to Stage B storage (MariaDB + Chroma); Grafana wiring + long-term backfill tooling remain.

- Fact Checker, Synthesizer, Chief Editor, Journalist Agents —
  `agents/fact_checker/`,`agents/synthesizer/`,`agents/chief_editor/`,`agents/journalist/` — Partial

- Intent: downstream processing — fact validation, summarization/synthesis, editorial suggestion, article drafting.

- Status: Several agents implemented; many functions have tests and tools but full integration and operational tuning
  remain ongoing. Fact Checker (and the adjacent Critic workflows) now share the Mistral-7B base via adapters so
  accuracy-critical reviews stay aligned with the broader rollout.

## Functional workflow patterns

1. Crawl & Extraction

  - Scheduler selects profiles (from `config/crawl_profiles/`) and posts jobs to crawler engine.

  - `crawler_engine`chooses strategy:`crawl4ai`(adaptive) preferred,`generic` fallback.

  - Crawl4AI returns pages or adaptive docs; these are converted into article dicts and passed to extraction pipeline.

1. HITL & Labeling

  - Shortlisting: articles that meet candidate criteria are packaged and sent to HITL via `_submit_hitl_candidates`.

  - Human/Programmatic Labelling: HITL service stores labels in `hitl_staging.db` and exposes endpoints for review and
    programmatic forwarding.

  - Forwarding: labels are forwarded to downstream ingestion (`memory.ingest_article`) with retry/backoff logic and
    ingestion-status transitions.

1. Ingestion & Persistence

  - `memory.ingest_article` handles content normalization, stores metadata in MariaDB, persists embeddings
    (Chroma/other), and signals archive storage.

  - Audit and raw_html storage allow re-extraction and verification.

1. Downstream Processing

- Agents like `fact_checker`,`synthesizer`and`chief_editor` run asynchronously on ingested articles, producing derived
  artifacts (checks, summaries, editor suggestions). Fact Checker and Critic now lean on the shared Mistral adapter
  stack for long-form reasoning while retaining lightweight retrieval models for evidence gathering.

1. Metrics & Observability

  - `crawl4ai_adapter._record_adaptive_metrics`emits adaptive
    metrics:`adaptive_runs_total`,`adaptive_confidence`,`adaptive_pages_crawled`,`adaptive_articles_emitted`.

  - Scheduler writes Prometheus textfile metrics; `infrastructure/` contains Prometheus scrape configs and Grafana
    dashboard templates.

## Training patterns

- Offline supervised training

- Use stored labeled examples (HITL outputs) and archived HTML to construct datasets for model training.
  `training_system/`and`training_system/tests` provide utilities and integration points.

- Online / continual training

- The system supports online training coordination via `common/online_training_coordinator.py` patterns and memory-based
  sampling for incremental updates.

- Human-in-the-loop feedback

- Labeled data from HITL is staged and can be used to retrain models (classification, extraction improvement, ranking).
  Use `agents/hitl_service` staging DB exports as dataset source.

- Evaluation-driven iteration

- Use `evaluation/` harness (added) to run extraction-parity checks (BLEU/ROUGE/F1/Levenshtein) against ground truth
  samples as acceptance criteria before rolling changes.

## Levels of completion — actionable summary

- High confidence / Done: `crawler_engine`core logic,`crawl4ai_adapter`,`extraction.py`, HITL API endpoints and
  migrations, scheduler dry-run. Tests exist for many core flows.

- Partial / Needs work: memory embedding pipeline, archive retention scripts, comprehensive site profile coverage, CI
  enforcement of `crawl4ai` availability, Grafana dashboards provisioning.

- Stub / Deprioritised: ultra-fast per-site crawlers (e.g., `bbc_crawler.py`) — recommended to deprecate and migrate to
  Crawl4AI profiles.

## Recommended next priorities (short term)

1. Enforce Crawl4AI availability in CI and runtime, add smoke tests (import + small adaptive run) — reduces drift
   between code and design.

1. Implement script registry for `js_code`reuse (`config/crawl_scripts/`+`agents/crawler/scripts_registry.py`).

1. Expand profile coverage: migrate remaining sites to per-site YAML in `config/crawl_profiles/`.

1. Harden HITL forwarding with deterministic retry/backoff and add staging acceptance tests verifying
   `ingestion_status='forwarded'`.

1. Provision dashboards and Prometheus job for adaptive metrics in `infrastructure/` and add parity evaluation CI job
   against stored fixtures.

## References and useful files

- Scheduler: `scripts/ops/run_crawl_schedule.py`

- Profiles: `config/crawl_profiles/*.yaml`

- Crawl4AI adapter: `agents/crawler/crawl4ai_adapter.py`

- Unified engine: `agents/crawler/crawler_engine.py`

- Extraction: `agents/crawler/extraction.py`

- HITL: `agents/hitl_service/` (FastAPI app, migrations)

- Evaluation harness: `evaluation/run_evaluation.py`,`evaluation/metrics.py`,`evaluation/datasets/`

- CI: `.github/workflows/pytest.yml`(CI uses`environment.yml` via micromamba in workflows)

--- This document is intended to evolve. To update it, edit `docs/architecture_overview.md` on your working branch and
submit a PR with context and test/CI changes as appropriate.
