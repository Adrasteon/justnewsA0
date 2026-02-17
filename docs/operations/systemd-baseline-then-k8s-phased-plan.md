--- title: "JustNews bring-up plan: systemd baseline and intelligence pipeline" description: "Authoritative action plan
to restore a fully working systemd deployment, harden ingestion quality, and stage fact-verification capabilities."
tags: ["runbook", "systemd", "gpu", "bring-up", "refactor-validation", "news- ingestion", "fact-checking"] ---

# JustNews bring-up plan: systemd baseline → intelligence pipeline

This plan restores the proven systemd deployment first, validates the refactor under known-good conditions, then layers
the ingestion, deduplication, and fact- verification capabilities required for the JustNews workflow. Each stage has
clear acceptance checks and rollback guidance.

> Repo note: This repo keeps systemd assets under `infrastructure/systemd/`. If documentation elsewhere refers
to`deploy/systemd/`, use the`infrastructure/systemd/` path here.

## Goals and definition of done (DoD)

- Fully working local/systemd deployment with:

- All core services healthy and reachable on localhost ports (8000–8014).

- GPU Orchestrator READY with models preloaded; NVIDIA MPS enabled (required) for GPU stability and isolation.

- Database initialized/migrated; health checks green; logs clean.

- Smoke tests pass; manual E2E flow succeeds (crawl → analyze → synthesize).

- High-quality ingestion pipeline capable of extracting clean article text, metadata, and embeddings across diverse
  publishers.

- Embedding storage for downstream clustering of cross-source coverage, with raw HTML retained for reprocessing.

- Fact extraction, corroboration, and Grounded Truth Value (GTV) scoring services online with APIs to inspect articles
  and facts.

- Rollback path at every phase back to stable systemd baseline.

- Transparent, auditable provenance for every article, fact, cluster, and synthesized publication.

## Prerequisites

- OS: Linux with systemd.

- GPU: NVIDIA drivers installed and healthy (`nvidia-smi` OK).

- Python: 3.11.x is the canonical target (3.12 remains experimental; see `requirements.txt`/`environment.yml`).

- Conda environment available: ${CANONICAL_ENV:-justnews-py312}.

- MariaDB: local or external (version per `infrastructure/systemd/setup_mariadb.sh`).

- Tooling: `git`,`curl`,`jq`,`psql`,`python`,`pip`(or conda),`virtualenv`.

- Content tooling: ensure packages for extraction and embeddings are available (`trafilatura`,`readability-
  lxml`,`jusText`,`extruct`,`langdetect`,`sentence-transformers`,`chromadb`). Pin versions in`requirements.txt` before
  deployment.

Required: NVIDIA MPS. MPS is an essential part of the design to protect GPU stability under concurrent workloads, reduce
memory fragmentation, and mitigate hard GPU crashes from OOM conditions and memory leaks.

## Stage A — Restore systemd baseline (authoritative path)

A0. Host cleanup (we already ran these during teardown)

- If you previously installed a lightweight Kubernetes (k3s) for legacy testing or POC, remove it to avoid service
  conflicts with systemd. This step is only necessary if you actually installed k3s; skip if not present:

- `/usr/local/bin/k3s-uninstall.sh`

- Verify: no `k3s.service`,`/run/k3s`, or`/var/lib/rancher/k3s` present.

- NOTE: Kubernetes manifests are deprecated and archived under `infrastructure/archives/kubernetes/`.

A1. Python environment

- Choose one:

- Virtualenv: create and activate, then `pip install -r requirements.txt`.

- Conda: `conda env create -f environment.yml`(if present), then`conda activate <env>`.

- Record the interpreter path (for systemd): set `JUSTNEWS_PYTHON`accordingly (e.g.,`/home/<you>/.venv/bin/python`).

A2. Secrets and config

- Global environment file for systemd: `/etc/justnews/global.env`:

- `JUSTNEWS_PYTHON=/abs/path/to/python`

- `SERVICE_DIR=/abs/path/to/repo/root`

- `JUSTNEWS_DB_URL=mysql://user:pass@localhost:3306/justnews`

- Optional GPU tuning: `ENABLE_MPS=true`

- Content pipeline configuration (same file or service-specific overrides):

- `UNIFIED_CRAWLER_ENABLE_HTTP_FETCH=true`

- `ARTICLE_EXTRACTOR_PRIMARY=trafilatura`

- `ARTICLE_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`

- `ARTICLE_URL_HASH_ALGO=sha256`

- `ARTICLE_URL_NORMALIZATION=strict`

- `CLUSTER_SIMILARITY_THRESHOLD=0.85`

- Per-service overrides (optional), e.g. `/etc/justnews/analyst.env`:

- `CUDA_VISIBLE_DEVICES=0`

- Any per-instance tuning or overrides supported by the units/scripts.

A3. Database

- Initialize local MariaDB (or point at an external DB):

- See `infrastructure/systemd/setup_mariadb.sh` for supported flows.

- Initialize/migrate schema (pick one, depending on repo conventions):

  - `scripts/setup_mariadb.sh`(recommended) or`scripts/setup_postgres.sh`(deprecated) then`scripts/init_database.py`

  - or run migrations in `database/migrations/` via your migration tool.

- Acceptance checks:

- DB reachable with `JUSTNEWS_DB_URL`.

- Application can connect (Memory/Archive services healthy once started).

A4. Install systemd artifacts

- Scripts (operator helpers):

- From `infrastructure/systemd/scripts/`, ensure these are executable and optionally copied to`/usr/local/bin/`:

  - `reset_and_start.sh`,`enable_all.sh`,`health_check.sh`,`cold_start.sh`,`wait_for_mcp.sh`,`justnews-start-
    agent.sh`,`justnews-preflight-check.sh`

- Units:

- From `infrastructure/systemd/units/`, copy unit templates to`/etc/systemd/system/`:

  - `justnews@.service` (if provided) and any service-specific units/targets.

  - Optional timers: `justnews-cold-start.timer`,`justnews-boot-smoke.timer`.

- Run `sudo systemctl daemon-reload` after copying.

- Optional drop-ins (tuning): `units/drop-ins/`→`/etc/systemd/system/justnews@<name>.service.d/`

- Examples: `05-gate-timeout.conf`(increase`GATE_TIMEOUT`), restart policies, etc.

A5. NVIDIA MPS (essential / required)

- Why required: MPS prevents class of GPU failures stemming from memory pressure, fragmentation, and leaks by
  multiplexing contexts; it dramatically reduces OOM-induced device resets. Keep it enabled for all stages in this plan.

- Start once per boot: `sudo nvidia-cuda-mps-control -d`.

- Set `ENABLE_MPS=true`globally; consider`ENABLE_NVML=true` for GPU Orchestrator env.

- Verify via Orchestrator endpoints after startup (below).

A6. Orchestrator-first startup (gated model preload)

- Preferred: single-command fresh bring-up

- `sudo infrastructure/systemd/scripts/reset_and_start.sh`

- Manual sequence:

- `sudo systemctl enable --now justnews@gpu_orchestrator`

- Wait for `http://127.0.0.1:8014/ready` to succeed

- `sudo infrastructure/systemd/scripts/enable_all.sh start`

- Acceptance checks:

- `infrastructure/systemd/scripts/health_check.sh` shows all green

- Ports 8000–8014 respond (see Quick Reference table)

- Orchestrator: `/ready`OK;`/models/status` shows preloaded models

A7. Baseline validation (refactor sanity)

- Run fast tests (unit + small integration): `pytest -q` (or project’s test runner)

- Hit health endpoints directly:

- `curl -fsS <http://127.0.0.1:8014/health`> (orchestrator)

- `curl -fsS <http://127.0.0.1:8000/health`> (mcp_bus), etc.

- `curl -fsS <http://127.0.0.1:8011/health`> (analytics — expects`{"status":"healthy"}` after the wrapper alias fix)

- Trigger a small end-to-end flow (minimal crawl → analyze → synthesize) and verify artifacts/logs.

- Capture a baseline diagnostics bundle (for regressions):

- Use any provided helpers under `infrastructure/systemd/scripts/`(e.g., status panels,`health_check.sh --panel`).

- Confirm MPS is active: `pgrep -x nvidia-cuda-mps-control` is running; Orchestrator MPS endpoints report enabled.

A8. Stabilize and document

- Record exact env versions (driver, CUDA, Python, package lockfiles).

- Save copies of `/etc/justnews/*.env` under ops secrets management.

- Confirm graceful shutdown: `sudo infrastructure/systemd/scripts/enable_all.sh stop`

Rollback (for Stage A):

- If services fail to stabilize, inspect logs: `journalctl -u justnews@<name> -e -n 200 -f`.

- Stop everything cleanly; free ports: `justnews-preflight-check.sh --stop`(or`preflight.sh --stop` if named so in your
  tree).

---

## Stage B — Ingestion quality and scheduler expansion

B0. Gating

- Stage A acceptance checks must be green. Baseline services stay under systemd control throughout this stage.

**Current Execution Plan (Nov 2025)**

- Run a controlled, non-test BBC crawl end to end to validate crawler → memory agent → MariaDB ingestion (watch
  scheduler metrics and raw HTML drops).

- Once ingestion is verified, port additional high-priority domains into `config/crawl_profiles/`, validating each with
  the probe script before enabling them in the schedule.

- With multiple sources ingesting cleanly, begin exercising the “Top X” workflow (clustering, fact search) using the new
  BBC-derived articles as seed data.

- 2025-11-02 status: canonical restart applied via `infrastructure/systemd/canonical_system_startup.sh`, BBC profile
  rerun with`scripts/ops/run_crawl_schedule.py --testrun`ingested 60/60 articles, zero ingestion errors, dedupe zero,
  Stage B metrics clean; evidence captured in`logs/analytics/crawl_scheduler_state.json` and sampler snippets stored in
  the bring-up ticket.

B1. Curated seed list and run scheduling

- Build `config/crawl_schedule.yaml`(or similar) enumerating priority sources, sections, update cadence, and per-run
  article caps. **Implementation note:** The repository now ships`config/crawl_schedule.yaml` with governance metadata
  for the primary cohorts.

- Define per-domain Crawl4AI profiles under `config/crawl_profiles/`(one YAML per domain) so operators can control
  depth, link filters, and JS automation without code changes. Align schedule cohorts with the matching profile slugs
  (e.g.,`standard_crawl4ai`,`deep_financial_sections`,`legacy_generic`).

- Implement an hourly scheduler (systemd timer or cron) that invokes the crawler agent with batched domain lists,
  respecting the global target of top **X** stories (default 500). **Implementation note:** Use
  `scripts/ops/run_crawl_schedule.py`+`infrastructure/systemd/scripts/run_crawl_schedule.sh`, driven by the`justnews-
  crawl-scheduler.timer` unit.

- Add health metrics: last successful run timestamp, domains crawled, articles accepted, scheduler lag. **Implemented
  via** Prometheus textfile output at `logs/analytics/crawl_scheduler.prom`(overridable) with
  gauges`justnews_crawler_scheduler_*`.

- Establish governance cadence: document source terms-of-use, rate limits, and review schedule (e.g., weekly curation
  audit). Track violations and remediation steps in an ops log (see `logs/governance/crawl_terms_audit.md`).

B2. High-precision extraction pipeline

- Integrate Trafilatura as the primary extractor inside the crawler agent; configure fallbacks (readability-lxml,
  jusText) invoked automatically when confidence is low. **Implemented via** `agents/crawler/extraction.py`, consumed
  by`GenericSiteCrawler`.

- Parse structured metadata using `extruct`(JSON-LD, microdata) and enrich results with publication date, authors,
  canonical URL, section tags, and language detection (`langdetect` or fastText). **Output propagated** through the
  crawler article payload and passed to ingestion.

- Persist raw HTML in blob storage or a dedicated column for forensic reprocessing and extractor improvements. **Raw
  artefacts now written** under `archive_storage/raw_html/`(override with`JUSTNEWS_RAW_HTML_DIR`).

- Add quality heuristics (minimum word count, boilerplate ratio, HTML sanity) and emit a “needs_review” flag when
  thresholds fail. **Heuristics configurable** via `ARTICLE_MIN_WORDS`/`ARTICLE_MIN_TEXT_HTML_RATIO`; failures bubble
  to`extraction_metadata.review_reasons`.

B3. Storage and schema updates

- Extend the articles table to include: `publication_date`,`authors`,`language`,`section`,`collection_timestamp`,`raw_ht
  ml_ref`,`extraction_confidence`,`url_hash`.

- Run `bash scripts/ops/apply_stage_b_migration.sh --record` to apply migration 003 and capture evidence in the ops log.

- Normalize URLs before hashing (lowercase host, strip tracking params, honor canonical tags) controlled by
  `ARTICLE_URL_NORMALIZATION`. Log original vs. normalized URL for audit.

- Compute per-URL hashes (algorithm configurable via `ARTICLE_URL_HASH_ALGO`) to block re-ingestion of the exact same
  article from the same source.

- Ensure ingestion payloads supply these fields; update the memory agent to upsert sources with enriched metadata.

- Record extractor provenance and version for reproducibility.

B4. Embedding generation and clustering preparation

- Package Sentence-BERT (`all-MiniLM-L6-v2`recommended) with a local cache; expose`ARTICLE_EMBEDDING_MODEL` env to
  switch models.

- Compute embeddings during ingestion; store in ChromaDB (or FAISS mirror for offline analysis).

- Defer cross-source clustering until each article completes fact-check scoring; embeddings are tagged with the latest
  GTV once Stage C runs so cluster creation can weight articles appropriately.

- Maintain metrics: embeddings generated, cluster candidate count (post Stage C), embedding latency, and model cache hit
  rate.

- **Implemented by** extended `StageBMetrics`counters/histograms consumed in`agents/memory/tools.save_article`; includes
  cache-label latency tracking and model availability counters.

B5. Validation and monitoring

- Regression tests: add fixtures with varied HTML to ensure extractor cascade behaves and metadata is captured.
  **Covered by** `tests/agents/crawler/test_extraction.py`and`tests/agents/crawler/test_generic_site_crawler.py`.

- Add integration tests covering scheduler-triggered crawl, ingestion, embedding computation, and duplicate suppression.

- Extend observability (Prometheus/Grafana panels) with extraction success rate, fallback usage, duplicate count, and
  article throughput trendlines.

- **Implemented by** `common/stage_b_metrics.StageBMetrics`counters consumed
  in`agents/crawler/extraction.py`and`agents/memory/tools.py`; validated
  via`tests/agents/crawler/test_extraction.py`and`tests/agents/memory/test_save_article.py`. Use
  the`docs/operations/stage_b_validation.md` playbook to coordinate dashboard updates and collect exit evidence.

- Launch a human-in-the-loop sampling program (by language/region) with QA dashboards to surface extractor drift.

- Publish governance dashboards tracking source coverage, robots compliance, and ingestion error budgets; alert when
  thresholds (e.g., >20% ingestion failures or QA alerts) are exceeded.

- Define rollback: disable scheduler timer and revert to manual crawl if errors exceed agreed threshold or governance
  alerts trigger.

B6. Automated crawl-profile author roadmap

- Goal: deliver a cron-driven service that fingerprints each source in the `sources`table, generates or adjusts
  its`config/crawl_profiles/<slug>.yaml`, validates the change, and promotes the update with evidence.

- Phase 0 (prereqs): catalogue current profiles, codify schema (JSONSchema + lint), stand up isolated test runner plus
  HTML snapshot store.

- Phase 1 (fingerprinting): Playwright-based sampler collects landing pages, link graphs, pagination hints, DOM metrics;
  artifacts versioned under `logs/operations/profile_author/` for diffing.

- Phase 2 (synthesis engine): heuristics convert fingerprints into draft profiles—start URLs, link filters,
  `target_elements`, adaptive knobs—rendered via template + schema validation with provenance metadata.

- Phase 3 (evaluation loop): execute short Crawl4AI runs against drafts, score recall/precision, auto-adjust selectors,
  and persist metrics (attempts, ingestion success, fallback usage) in a dedicated table for trend tracking.

- Phase 4 (drift detection): nightly job compares fresh fingerprints to baselines, triggers re-generation when DOM
  hashes or ingestion failure rate exceed thresholds, and stores profile versions with diff reports.

- Phase 5 (operations): integrate with systemd timer/cron, emit Prometheus counters, open change requests when
  automation confidence < approved threshold, and maintain manual override path. Wire dashboards to show last profile
  refresh, drift alerts, and pending operator reviews.

- Rollout gating: keep automation in shadow mode until it produces two consecutive clean runs (zero ingestion errors,
  recall within tolerance) for BBC baseline; expand cohort-by-cohort with ops sign-off.

Exit criteria for Stage B:

- Scheduler reliably delivers top-X articles each run with success metrics logged.

- Extracted articles contain clean body text with metadata populated; quality heuristics show <5% “needs_review”.

- URL-hash dedupe prevents same-source re-ingestion; embeddings stored in pg_vector for clustering with preliminary
  cluster candidate metrics published.

- Baseline Stage A health remains stable under continuous operation.

--- STOP HERE UNTIL INGESTION QUALITY TARGETS ARE ACHIEVED ---

## Stage C — Fact intelligence and Grounded Truth

C0. Foundations

- Stage A and Stage B acceptance criteria must hold. Fact intelligence components run as systemd services or background
  workers with clear restart policies.

C1. Fact extraction pipeline

- Deploy a dedicated NLP service (spaCy/transformers) to run NER and relation extraction on newly ingested articles.

- Produce structured claims with entity spans, relation types, temporal context, and extractor confidence.

- Persist outputs in a new `facts_to_check`table linked to`articles` via foreign key.

C2. Evidence graph storage

- Create supporting tables for claims, evidence sources, verification status, and audit metadata (who/what verified,
  timestamps, confidence scores).

- Index by entities and topics to accelerate downstream queries; store signed digests or checksums for evidence
  artifacts to ensure tamper-evident histories.

- Mirror outputs to the transparency archive at `archive_storage/transparency/` (facts, clusters, articles, evidence)
  with deterministic JSON to keep public audit trails in sync.

- Update `archive_storage/transparency/index.json` as part of each ingestion batch for transparency portal freshness
  reporting.

C3. Corroboration workflows and clustering

- Implement automated web search agent(s) that craft targeted queries per fact, evaluate snippet authority, and capture
  confirming vs. contradicting references.

- After each article receives its Grounded Truth Value, run clustering jobs on embeddings. Persist cluster metadata
  (member URLs, representative embedding, consensus headline) along with aggregated GTV weights for downstream
  synthesis.

- Add media verification pipeline: reverse image search, basic deepfake detection, and transcript validation for
  audiovisual references.

- Store evidence artifacts (URLs, media hashes, tool outputs) alongside provenance notes. Maintain public-facing audit
  trails so end users can inspect the chain of evidence per fact or cluster.

- Monitor bias metrics (source diversity, geographic representation, ideological balance) per cluster; flag clusters
  that over-rely on a single perspective.

C4. Grounded Truth scoring engine

- Define weighted scoring model (W1..W4) configurable via environment or database settings.

- Recompute GTV when new evidence arrives or source reputation changes.

- Expose real-time metrics: score distribution, pending verifications, conflicting evidence count.

C5. API and review tools

- Extend the API layer to serve:

- Top-X articles for the latest run with quality metadata.

- Facts for a given article, including GTV and evidence summaries.

- Search endpoints for entities/topics and their verification status.

- Provide operator dashboards for manual adjudication of low-confidence facts with the ability to override scores while
  retaining audit trails.

C6. Testing, criteria, and rollback

- Unit/integration tests covering claim extraction, search agent interactions (with mocked external APIs), scoring
  accuracy, and API responses.

- Load-test fact pipelines with a full run’s worth of articles to ensure throughput goals.

- Rollback path: disable fact scheduler and isolate services if verification error rate spikes; ingestion continues
  unaffected.

Exit criteria for Stage C:

- Facts extracted and stored for the majority of ingested articles.

- Automated corroboration retrieves third-party evidence for priority claims.

- Clusters published for major stories with consolidated metadata ready for synthesis.

- GTV scores available through API/dashboard with monitoring on latency and accuracy.

- Evidence audit APIs expose source documents, verification steps, and scoring rationale for each fact/cluster.

- Operators have clear playbooks for manual intervention, bias remediation, and error handling.

--- STOP HERE UNTIL FACT INTELLIGENCE AND TRANSPARENCY TARGETS ARE ACHIEVED ---

## Stage D — Synthesis, publishing, and transparency

D0. Foundations

- Stages A–C must be stable. Editorial and publishing services run with audit logging enabled.

D1. Weighted synthesis pipeline

- Consume cluster outputs and GTV-weighted facts to draft unbiased articles via synthesis agent or editorial tooling.

- Make weighting logic explicit: record which facts were emphasized, suppressed, or excluded with reasons tied to GTV
  and bias metrics.

- Block synthesis readiness until `/transparency/status`returns`integrity.status`of`ok`or`degraded`; fail start when
  transparency audits are unavailable.

- Systemd baseline: ensure `EVIDENCE_AUDIT_BASE_URL=http://localhost:8013/transparency` so the synthesizer gate hits the dashboard agent’s evidence
  API before reporting ready.

D2. Editorial review and ethics compliance

- Provide human editor workbench to review synthesized drafts, adjust weights, and approve publication.

- Log reviewer actions, comments, and final decisions for downstream audits.

D3. Publication workflow

- Automate push to website/CMS with metadata linking back to underlying clusters, evidence, and fact trails.

- Expose an end-user transparency portal where readers can inspect supporting sources, evidence status, and verification
  chronology.

- Back the transparency portal via the dashboard agent’s `/transparency`API
  (see`agents/dashboard/transparency_repository.py`) fed from the archive mirror.

D4. Post-publication monitoring

- Track reader feedback, correction requests, and post-publication fact challenges; integrate into governance
  dashboards.

- Monitor synthesized article bias metrics and re-run clustering/verification when new facts emerge.

- Ship Grafana transparency governance dashboard
  (`monitoring/dashboards/generated/transparency_governance_dashboard.json`) for coverage, evidence completeness, bias,
  and latency monitoring.

D5. Operational guardrails

- Define error budgets for synthesis latency, evidence retrieval failures, and transparency portal uptime.

- Alert and auto-suspend publication pipeline when transparency requirements (e.g., missing evidence links) fall below
  thresholds.

Exit criteria for Stage D:

- Synthesis pipeline produces articles with documented weighting rationale and editor sign-off.

- Transparency portal exposes source evidence, verification steps, and bias metrics per published article.

- Operational guardrails active with dashboards/alerts covering synthesis, transparency, and reader feedback loops.

--- STOP HERE UNTIL PUBLISHING & TRANSPARENCY TARGETS ARE ACHIEVED ---

---

## Acceptance checklist (quick)

- Systemd baseline

- [ ] Orchestrator READY; models preloaded

- [ ] All services healthy on ports 8000–8014

- [ ] DB connected; basic E2E flow passes

- [ ] Logs clean; health panel green

- [ ] NVIDIA MPS daemon running and reported enabled by Orchestrator

- Ingestion pipeline

- [ ] Scheduler delivers hourly top-X crawl with success metrics

- [ ] Trafilatura-first extractor returns clean article bodies; fallbacks logged <5%

- [ ] Metadata fields (publication_date, authors, language, section, url_hash, normalized_url) populated for >90% of
  articles

- [ ] URL hash dedupe prevents same-source re-ingestion; embeddings stored with clustering metrics exposed

- [ ] Governance dashboards active; human QA sampling program operational

- Fact intelligence

- [ ] facts_to_check table populated with entities/claims per new article

- [ ] External corroboration jobs producing evidence records

- [ ] Cluster records created with representative embeddings and member URLs

- [ ] GTV scores computed and accessible via API/dashboard; evidence audit APIs exposed publicly

- [ ] Bias monitoring dashboards active; monitoring alerts defined for ingestion, clustering, verification, and
  transparency regressions

- Publishing & transparency

- [ ] Weighted synthesis pipeline operational with editor approval workflow

- [ ] Transparency portal live with per-article evidence and bias disclosures, backed by `archive_storage/transparency`

- [ ] Post-publication monitoring/feedback loop feeding governance dashboards

## Appendix: Useful paths in this repo

- Systemd docs:

- `infrastructure/systemd/COMPREHENSIVE_SYSTEMD_GUIDE.md`

- `infrastructure/systemd/DEPLOYMENT.md`

- `infrastructure/systemd/QUICK_REFERENCE.md`

- Scripts:

- `infrastructure/systemd/scripts/enable_all.sh`

- `infrastructure/systemd/scripts/reset_and_start.sh`

- `infrastructure/systemd/scripts/cold_start.sh`

- `infrastructure/systemd/scripts/health_check.sh`

- `infrastructure/systemd/setup_mariadb.sh`

- Content pipeline assets:

- `config/` (seed list, crawl schedule, extractor settings)

- `agents/sites/` (extractor implementations and fallbacks)

- `agents/memory/` (ingestion + embeddings logic)

- `docs/data-pipeline/` (if present, specifications for facts and GTV)

- Units (examples):

- `infrastructure/systemd/units/justnews-*.service`

- `infrastructure/systemd/units/justnews-*.timer`

- `infrastructure/systemd/units/justnews-crawlers.target`

---
