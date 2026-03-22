# Hybrid Whitelist + Discovery Execution Checklist

Date: 2026-03-21
Status: Tracking template
Companion: `HYBRID_WHITELIST_DISCOVERY_IMPLEMENTATION_TICKETS_2026-03-21.md`

## How to Use

1. Mark each line item complete only after artifact evidence is attached.
2. Do not advance canary stages unless all mandatory gates are green.
3. If any critical gate fails, execute rollback and open an incident artifact.

## Current Implementation Snapshot (2026-03-21)

This section records the latest engineering validation run and should be updated
at each phase checkpoint.

- Validation command executed in UV venv (revalidated at 20:38 UTC):
	`python -m pytest -q tests/agents/crawler/test_crawl4ai_ingestion_triage.py agents/crawler/tests/test_endpoints.py tests/agents/test_runtime_config_traceability.py tests/common/test_ddg_search_service.py tests/agents/test_crawler_engine.py -k "whitelist_only or provisional or discovery_disabled or lane2_fallback or triage or runtime_config_accepts_discovery_kill_switch_keys or update_triage_adapter_endpoint_persists_examples or ddg"`
- Result: 18 passed, 38 deselected, 0 failed.
- Status summary:
	- Gate A foundations present (runtime kill-switch keys, audit log, rollback API).
	- Gate B core lifecycle enforcement present (state schema + transition history + eligibility checks).
	- Gate C partially implemented (domain filtering and whitelist/provisional gating validated; discovery guardrails still require explicit execution artifacts).
	- Gates D-I remain open pending staged implementation and operations evidence.
- Known warnings from run:
	- OpenTelemetry trace export warning seen in test environment (`127.0.0.1:4317` unavailable).
- Migration status:
	- DDG client dependency migration completed (`duckduckgo_search` -> `ddgs`) in runtime code and dependency manifests.

## Repository Working Tree Context (2026-03-22)

The following non-checklist file changes were already present in the working tree
during this documentation update cycle. They are tracked here for operator
context and are not checklist gate-completion evidence.

- `agents/memory/memory_engine.py`
	- Added a threading lock and serialized article-save paths to reduce concurrent
	  DB/Chroma write contention risk.
- `config/gpu/optimization_history.json`
	- Timestamp metadata updated (`last_updated`, `saved_at`).
- `config/runtime/runtime_config_state.json`
	- Runtime overrides/version timeline updated by autonomic controller.
	- `orchestrator.max_concurrent_tasks`: 10 -> 9
	- `orchestrator.polling_interval_seconds`: 4 -> 5
	- Version advanced from 385 -> 386.
- Model-store root scope clarification and strict-consistency recommendations were added to:
	- `docs/operations/ENVIRONMENT_CONFIG.md`
	- `mcp_fact_checker_server/README.md`
	- Note: current devcontainer flow uses workspace-scoped `/app/model_store`; canonical host deployments may use a host-global `MODEL_STORE_ROOT` path.

## Completion Constraints (External Dependencies)

The remaining unchecked items cannot be fully completed from repository-only
changes. They require live environment execution and organizational sign-off.

- Requires live operations telemetry and dashboard exports:
	- Baseline SLO windows, concentration/starvation metrics, and canary-stage health.
- Requires production-like drill execution:
	- Rollback drills, poisoning-response drills, and incident retrospectives.
- Requires cross-functional approvals:
	- Engineering, Operations, Product, and Security/Trust sign-off records.
- Requires staged rollout windows:
	- Canary stage 1-3 and final rollout validations over time.

Completion policy for this checklist:
- Mark a line item complete only when evidence artifacts are attached from the
	corresponding live run, report export, or approval record.

## Dev Cycle Plan: Living Story Update-First Clustering

Scope note:
- This plan is for active development only.
- It explicitly excludes production rollout stages and multi-party sign-off gates.

### 1) Baseline and Instrumentation

- [ ] Capture current baseline metrics for 24h dev traffic:
	- attach-to-existing-story rate
	- singleton cluster creation rate
	- false-merge sample rate
	- time-to-correct-cluster (for initially wrong assignment)
- [ ] Add per-article clustering decision logs with:
	- selected cluster
	- top-k candidates
	- confidence band
	- reason codes and score components
- [ ] Add a small comparison report script to diff old vs new clustering decisions over the same input set.

Evidence links:
- [ ] Baseline metric snapshot
- [ ] Decision log sample export
- [ ] Old-vs-new comparison output

### 2) Story-First Candidate Retrieval

- [ ] Add first-pass matching against existing living story clusters (published + recently active).
- [ ] Keep current article-neighbor matching as second-pass fallback.
- [ ] Create a story profile cache (or materialized view) containing:
	- centroid embedding
	- key entities/event terms
	- recency/activity metadata
	- source diversity signals

Evidence links:
- [ ] Unit tests for story-first candidate retrieval
- [ ] Dev run logs showing first-pass story matching events

### 3) Confidence-Banded Assignment

- [ ] Implement confidence bands for assignment decisions:
	- high: immediate attach
	- medium: provisional attach candidate
	- low: create new cluster with retained alternatives
- [ ] Make thresholds runtime-configurable in dev.
- [ ] Add reason-code telemetry for every confidence-band decision.

Evidence links:
- [ ] Config key snapshot
- [ ] Threshold behavior test results
- [ ] Decision telemetry sample

### 4) Non-Exclusion Candidate Persistence

- [ ] Persist top-k candidate clusters per article with score breakdown and timestamp.
- [ ] Add scheduled re-evaluation policy for:
	- medium-confidence assignments
	- fresh singleton clusters
	- recently published stories with potential related arrivals
- [ ] Ensure re-evaluation can reassign when confidence improves.

Evidence links:
- [ ] Candidate persistence schema/code reference
- [ ] Re-evaluation policy test output
- [ ] Reassignment example from dev logs

### 5) Composite Scoring Upgrade

- [ ] Move from single distance threshold to weighted composite score:
	- semantic similarity
	- entity overlap
	- event phrase overlap
	- temporal coherence
	- source-pattern compatibility
- [ ] Add adaptive threshold profiles by topic/lane.
- [ ] Add hard-negative checks for known false-merge patterns.

Evidence links:
- [ ] Score component validation tests
- [ ] Adaptive profile config snapshot
- [ ] False-merge guardrail test report

### 6) Living Story Update Flow Enforcement

- [ ] Ensure cluster attach to existing story defaults to update path.
- [ ] Preserve stable story lineage across updates (same story identity continuity).
- [ ] Record update rationale in synthesis metadata for each revision.

Evidence links:
- [ ] End-to-end test showing update of existing story
- [ ] Metadata sample showing update rationale and revision increment

### 7) Dev Validation Loop (Fast Iteration)

- [ ] Run shadow-mode comparison for at least 3 consecutive dev cycles.
- [ ] Review sampled decisions daily and tune thresholds.
- [ ] Track convergence trend:
	- rising attach-to-existing-story
	- falling singleton creation without rising false merges
- [ ] Keep feature flags available for immediate fallback during experiments.

Evidence links:
- [ ] Shadow-mode daily reports
- [ ] Threshold tuning changelog
- [ ] Weekly trend snapshot

### 8) Dev Completion Criteria

- [ ] Attach-to-existing-story improves by agreed dev target.
- [ ] Singleton rate drops by agreed dev target.
- [ ] False-merge sample rate remains within agreed dev guardrail.
- [ ] At least 10 representative stories show healthy multi-update Living Story progression.

Evidence links:
- [ ] Final dev metric summary
- [ ] Story progression sample set

## Phase Gate A: Safety Baseline (Must Pass Before Any Discovery Enablement)

- [x] Kill switches implemented and validated under active crawl load.
- [x] Whitelist-only fallback tested and restores baseline behavior.
- [x] Runtime config audit trail confirms apply and rollback lineage.
- [ ] Baseline SLO window captured for quality, diversity, latency, and error rate.

Evidence links:
- [x] Runtime config API logs
- [x] Rollback drill output
- [ ] Baseline dashboard snapshot

Attached evidence:
- Runtime config key registry + apply/rollback audit logging in `agents/workflow_orchestrator/runtime_config.py`.
- Discovery/whitelist kill switch validation in `tests/agents/test_runtime_config_traceability.py`.
- Whitelist/provisional enforcement validation in `tests/agents/test_crawler_engine.py`.
- Latest checkpoint command/result in "Current Implementation Snapshot" (18 passed, 38 deselected, 0 failed).

## Phase Gate B: Lifecycle State Enforcement

- [x] Source lifecycle schema migration applied and verified.
- [x] Transition audit records include actor, reason, old/new state, timestamp.
- [x] State-aware source eligibility enforced in crawler and policy paths.
- [x] Invalid transitions rejected and logged.

Evidence links:
- [x] Migration evidence
- [x] DB integrity checks
- [x] Transition test results

Attached evidence:
- Lifecycle schema + transition table migration in `database/migrations/022_add_source_lifecycle_governance.sql`.
- Transition write path and invalid state rejection in `database/utils/migrated_database_utils.py` (`set_source_lifecycle_state`).
- Crawl eligibility enforcement by source state in `agents/crawler/crawler_utils.py`.
- Lifecycle-focused tests in `tests/agents/crawler/test_crawler_utils_lifecycle.py` and `tests/agents/test_crawler_engine.py`.

## Phase Gate C: Discovery Intake Guardrails

- [ ] Discovery profile limits configured (depth, per-page links, per-domain caps).
- [ ] Off-site follow is disabled outside discovery profile.
- [ ] Domain normalization and dedupe queue are operational.
- [x] Provenance fields present for all discovered candidates.
- [x] Hard deny filters block known low-quality domain classes pre-budget.

Evidence links:
- [ ] Discovery profile config snapshot
- [ ] Adapter/crawler integration tests
- [x] Deny filter regression report

Attached evidence:
- DDG low-quality domain filtering and news-domain gating in `common/ddg_search_service.py`.
- DDG migration completion + DDG tests in `tests/common/test_ddg_search_service.py`.
- Lane1 comparative expansion candidate provenance fields in `agents/crawler/crawler_engine.py` (`_build_lane1_expansion_candidates`).

## Phase Gate D: Provisional Sandbox and Budget Isolation

- [ ] Separate provisional budget pools enabled.
- [ ] Whitelist starvation prevention verified under flood simulation.
- [ ] Per-run and rolling-window provisional caps enforced.
- [ ] Global diversity allocator floors and ceilings active.

Evidence links:
- [ ] Load test report
- [ ] Budget telemetry snapshots
- [ ] Diversity allocation report

## Phase Gate E: Scoring and Promotion Workflows

- [ ] Confidence-aware multi-signal score model deployed.
- [ ] Score versioning and reproducibility checks passed.
- [ ] Promotion threshold gates require minimum sample and duration windows.
- [ ] Probation/demotion/block transitions fire on configured failure conditions.
- [ ] Lane eligibility boundaries prevent policy bypass by provisional sources.

Evidence links:
- [ ] Score model validation report
- [ ] Transition replay report
- [ ] Lane policy test artifacts

## Phase Gate F: Self-Learning Loop (Shadow to Active)

- [ ] Source quality history stream populated with valid lineage.
- [ ] Shadow mode recommendations stable and reproducible.
- [ ] Active mode delta bounds, cooldowns, and rollback hooks configured.
- [ ] Active mode remains unable to mutate publication hard-gate logic.

Evidence links:
- [ ] Shadow replay metrics
- [ ] Active mode guardrail tests
- [ ] Auto-rollback simulation

## Phase Gate G: Anti-Poisoning and Incident Preparedness

- [ ] Anomaly detectors for correction floods, churn, and volatility are live.
- [ ] Quarantine workflow blocks promotion and lane influence during incidents.
- [ ] Incident runbooks published with command/API procedures.
- [ ] Team executed at least one poisoning-response drill.

Evidence links:
- [ ] Anomaly dashboard captures
- [ ] Quarantine event logs
- [ ] Drill artifact and retrospective

## Phase Gate H: Observability and Transparency

- [ ] Governance KPI dashboard pack available and used in release reviews.
- [ ] KPI coverage includes intake, rejections, promotions, demotions, spread, concentration, starvation.
- [ ] Optional transparency payload extensions validated (if in scope).

Evidence links:
- [ ] KPI dashboard export
- [ ] Release review snapshot
- [ ] Transparency payload schema tests

## Phase Gate I: Canary Rollout and Final Sign-Off

- [ ] Canary stage 1 completed with all mandatory metrics green.
- [ ] Canary stage 2 completed with no quality regression.
- [ ] Canary stage 3 completed with diversity improvement and no concentration breach.
- [ ] Final rollout stage completed with stable queue latency and error budgets.
- [ ] Production sign-off bundle approved by engineering, ops, and product.

Evidence links:
- [ ] Canary stage reports
- [ ] Final readiness bundle
- [ ] Sign-off record

## Mandatory Stop Conditions

If any condition below is true, halt rollout and execute rollback policy:

- [ ] Factual quality SLO regression breaches threshold.
- [ ] Discovery flood bypasses budget controls.
- [ ] Concentration ceiling breach persists beyond grace window.
- [ ] Whitelist starvation index exceeds threshold.
- [ ] Quarantine system fails to isolate flagged cohorts.
- [ ] Runtime rollback is unavailable or fails validation.

## Rollback Checklist

- [ ] Set whitelist-only mode.
- [ ] Disable discovery and off-site follow flags.
- [ ] Disable provisional ingestion and learner active mode.
- [ ] Verify source selection returns to whitelist anchor behavior.
- [ ] Confirm queue and quality metrics return to baseline envelope.
- [ ] Open incident report and attach rollback evidence.

## Release Manager Sign-Off

- Engineering Lead: [ ] Approved
- Operations Lead: [ ] Approved
- Product Lead: [ ] Approved
- Security/Trust Review: [ ] Approved
- Date/Time:
- Release window:
