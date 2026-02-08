# Crawler Agent — Design and Interfaces

This document expands the `Crawler` agent responsibilities, internal components, configuration, and sequence flows. It
is intended for engineers implementing or extending crawl behavior.

Files of interest

- `agents/crawler/crawler_engine.py` — unified engine and orchestration

- `agents/crawler/crawl4ai_adapter.py` — Crawl4AI translation layer

- `agents/sites/generic_site_crawler.py` — fallback crawler

- `config/crawl_profiles/` — per-site YAML profiles

Responsibilities

- Accept crawl jobs (from scheduler) containing profile overrides and targets.

- Determine the execution strategy (adaptive Crawl4AI, synchronous Crawl4AI, or generic fallback).

- Execute crawl runs, convert results into the project's article shape, and invoke the extraction pipeline.

- Submit candidate articles to HITL where configured and await/handle forwarding decisions.

- Invoke `memory.ingest_article` for final ingestion after HITL or directly when no HITL required.

- Emit adaptive metrics and telemetry for observability.

Key components

- Strategy selector (`_determine_optimal_strategy`): heuristic + profile flags.

- Crawl runner: calls `crawl4ai_adapter.crawl_site_with_crawl4ai`(async) or`GenericSiteCrawler` (sync).

- Result normaliser: `_build_article_from_result`/`_build_article_from_adaptive_doc` convert C4A outputs into article
  dicts.

- HITL submitter: `_submit_hitl_candidates` constructs payload and posts to HITL. Implements retries/backoff.

- Ingest caller: `_ingest_articles`calls MCP Bus`memory.ingest_article` with final payload.

Configuration and profiles

- Profiles control `browser_config`,`run_config`(cache_mode, wait_for,
  js_code),`adaptive`block,`link_preview`rules,`start_urls`,`follow_internal_links`, and`max_pages`.

- `config/crawl_profiles/base.yaml` provides defaults; per-site files override fields.

APIs and payload shapes (excerpt)

- HITL candidate payload (keys used):

- `id`(string),`url`,`site_id`(string),`title`,`extracted_text`(truncated),`extraction_metadata`(dict),`publish_time`
  (iso)

- MCP call `memory.ingest_article` payload (example):

- `site_id`,`url`,`title`,`cleaned_text`,`extraction_metadata`,`source_html_path`,`ingest_meta`

Sequence: Crawl → HITL → Ingest (summary)

1. Scheduler posts job with profile.

1. `crawler_engine` determines strategy and calls adapter/runner.

1. Runner fetches pages; extraction pipeline produces `article` dicts.

1. For candidates, engine calls HITL service with payloads.

1. HITL labels and (if forwarded) engine calls `memory.ingest_article` for ingestion.

Testing & acceptance

- Smoke tests: import `crawl4ai` and run a short adaptive digest using a benign profile.

- Extraction parity: run `evaluation/run_evaluation.py` on stored samples to validate Trafilatura-first extraction
  parity.

Extensibility notes

- Script registry: new `js_code`should be referenced by slug; implement`agents/crawler/scripts_registry.py` to resolve
  script content.

- Adaptive tuning: expose adaptive thresholds and telemetry tags in profiles to help scoring and profiling.
