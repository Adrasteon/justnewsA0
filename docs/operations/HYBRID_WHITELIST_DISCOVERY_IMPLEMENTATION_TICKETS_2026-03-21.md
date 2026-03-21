# Hybrid Whitelist + Discovery Implementation Tickets

Date: 2026-03-21
Status: Implementation-ready
Audience: Engineering, Operations, Product, Release Management

## Objective

Implement a hybrid source acquisition model that uses a curated whitelist as the trust anchor while enabling controlled off-site discovery for global breadth, without allowing low-quality domain floods or policy bypass.

## Non-Negotiable Invariants

1. Whitelist-only mode must remain one-switch rollback behavior at all times.
2. No discovered source can bypass provisional lifecycle stages.
3. Learning/ranking updates cannot weaken publication hard gates.
4. Flood prevention must fail safe toward under-ingestion, not over-ingestion.

## Program Execution Model

1. Rollout is phased and reversible.
2. Safety controls and observability land before behavior changes.
3. Every ticket has explicit owner boundary, dependencies, and acceptance criteria.

## Epic 0: Safety Baseline + Rollback First

### E0-T1: Global Kill Switches and Safe Defaults

- Owner: Platform + Workflow
- Depends on: none
- Scope:
  - Add runtime flags for discovery on/off, off-site follow on/off, provisional ingest on/off, whitelist-only enforcement.
  - Ensure defaults are fail-safe on service startup.
- File targets:
  - `agents/workflow_orchestrator/runtime_config.py`
  - `agents/workflow_orchestrator/engine.py`
  - `agents/crawler/crawler_engine.py`
- Acceptance criteria:
  - Any switch takes effect within one runtime config polling cycle.
  - Whitelist-only mode bypasses all discovered-domain paths.
  - Runtime audit entries are emitted for patch/apply/rollback.

### E0-T2: Baseline SLO and Blast Radius Contract

- Owner: Analytics + Ops
- Depends on: E0-T1
- Scope:
  - Define baseline windows and stop conditions for quality, diversity, queue latency, and error rates.
  - Publish rollout go/no-go thresholds.
- File targets:
  - `agents/analytics/analytics_engine.py`
  - `docs/operations/README.md`
- Acceptance criteria:
  - Baseline metrics are queryable and documented.
  - Stop conditions are actionable by on-call operators.

## Epic 1: Source Lifecycle Governance

### E1-T1: Lifecycle Schema and Transition Audit

- Owner: Data + Backend
- Depends on: E0-T1
- Scope:
  - Add lifecycle state persistence and immutable transition log.
  - Add DB utility methods for transitions with actor/reason metadata.
- File targets:
  - `database/migrations/` (new migration)
  - `database/utils/migrated_database_utils.py`
- Acceptance criteria:
  - States: `trusted_whitelist`, `provisional_discovered`, `candidate_review`, `trusted_promoted`, `probation`, `blocked`.
  - All state transitions are auditable with previous and new state.

### E1-T2: State-Aware Crawl Eligibility

- Owner: Crawler + Workflow
- Depends on: E1-T1
- Scope:
  - Enforce state-based source eligibility and budget constraints.
  - Prevent blocked/provisional state leakage into trusted paths.
- File targets:
  - `agents/crawler/crawler_utils.py`
  - `agents/crawler/crawler_engine.py`
  - `agents/workflow_orchestrator/policies.py`
- Acceptance criteria:
  - Probation sources auto-throttle.
  - Provisional/blocked sources cannot satisfy verified eligibility.

## Epic 2: Controlled Off-Site Discovery Intake

### E2-T1: Discovery Crawl Profile + Off-Site Guardrails

- Owner: Crawler
- Depends on: E0-T1
- Scope:
  - Add discovery profile with shallow off-site traversal and strict caps.
  - Enforce per-page/per-domain off-site link and redirect limits.
- File targets:
  - `config/crawl_profiles/base.yaml`
  - `agents/crawler/crawl4ai_adapter.py`
- Acceptance criteria:
  - Off-site follow only in discovery profile.
  - Link volume limits are deterministic under high-link pages.

### E2-T2: Discovered Domain Intake Queue with Provenance

- Owner: Crawler + Data
- Depends on: E2-T1, E1-T1
- Scope:
  - Normalize discovered domains to canonical keys.
  - Persist provenance (referrer, topic, region/language hints, timestamp).
- File targets:
  - `agents/crawler/crawl4ai_adapter.py`
  - `agents/crawler/crawler_engine.py`
  - `database/utils/migrated_database_utils.py`
- Acceptance criteria:
  - Duplicate domains collapse by canonical key.
  - Provenance exists for every discovery candidate.

### E2-T3: Hard Deny Filters Pre-Budget

- Owner: Policy + Crawler
- Depends on: E2-T2
- Scope:
  - Add versioned low-quality domain filters with reason taxonomy.
  - Reject social/forum/link-farm/dictionary/scraper classes before crawl spend.
- File targets:
  - `common/ddg_search_service.py`
  - `agents/crawler/crawl4ai_adapter.py`
  - `agents/workflow_orchestrator/policies.py`
- Acceptance criteria:
  - Rejected domains consume zero crawl budget.
  - Rejection metrics are observable by reason.

## Epic 3: Provisional Sandbox + Budget Isolation

### E3-T1: Provisional Budget Pools and Starvation Protection

- Owner: Crawler
- Depends on: E1-T2, E2-T2
- Scope:
  - Create separate budget pools for discovery and whitelist paths.
  - Reserve whitelist minimum capacity under all conditions.
- File targets:
  - `agents/crawler/crawler_engine.py`
  - `agents/workflow_orchestrator/runtime_config.py`
- Acceptance criteria:
  - Discovery cannot starve whitelist throughput.
  - Provisional caps enforced per run and rolling window.

### E3-T2: Global Diversity Allocator

- Owner: Workflow + Analytics
- Depends on: E3-T1
- Scope:
  - Add quota floors for underrepresented regions/languages/topics.
  - Add concentration ceilings by domain and owner group.
- File targets:
  - `agents/workflow_orchestrator/policies.py`
  - `agents/analytics/analytics_engine.py`
- Acceptance criteria:
  - Allocation report per crawl cycle.
  - Ceiling breaches trigger automatic throttling.

## Epic 4: Source Quality Scoring + Promotion Workflow

### E4-T1: Confidence-Aware Multi-Signal Scoring

- Owner: Data Science + Backend
- Depends on: E3-T1
- Scope:
  - Compute score from factual outcomes, extraction quality, correction burden, reliability, and access friction.
  - Apply confidence bounds to low-sample domains.
- File targets:
  - `agents/workflow_orchestrator/policies.py`
  - `agents/crawler/crawler_utils.py`
  - `database/utils/migrated_database_utils.py`
- Acceptance criteria:
  - Scoring is deterministic and version-tagged.
  - Low sample sources remain constrained.

### E4-T2: Promotion, Probation, Demotion, Block Automation

- Owner: Workflow + Data
- Depends on: E4-T1, E1-T1
- Scope:
  - Add rolling-window transition logic and minimum evidence gates.
  - Auto-probation and demotion triggers for drift and anomalies.
- File targets:
  - `agents/workflow_orchestrator/policies.py`
  - `database/utils/migrated_database_utils.py`
- Acceptance criteria:
  - No promotion before sample-size and duration thresholds.
  - High-severity anomalies force probation.

### E4-T3: Lane-Aware Source Eligibility Boundaries

- Owner: Workflow + Publisher Policy
- Depends on: E4-T2
- Scope:
  - Keep stricter source requirements for verified lane than developing lane.
  - Enforce opinion vs factual corroboration boundaries.
- File targets:
  - `agents/workflow_orchestrator/policies.py`
  - `agents/crawler/crawler_engine.py`
- Acceptance criteria:
  - Provisional/probation sources do not satisfy verified factual minima.
  - Attributed opinion contributes to perspective coverage only.

## Epic 5: Self-Learning Source Ranking Loop (Constrained)

### E5-T1: Source Quality History Stream

- Owner: Data + Training System
- Depends on: E4-T1
- Scope:
  - Persist time-series source outcomes and correction feedback.
  - Validate signal provenance at ingest.
- File targets:
  - `database/migrations/` (new migration)
  - `database/utils/migrated_database_utils.py`
  - `training_system/core/system_manager.py`
- Acceptance criteria:
  - Every score update maps to evidence lineage.
  - Invalid signal payloads are rejected with diagnostics.

### E5-T2: Shadow Mode Ranking Learner

- Owner: Training System + Workflow
- Depends on: E5-T1
- Scope:
  - Produce ranking recommendations without live actuation.
  - Emit stability and drift diagnostics.
- File targets:
  - `training_system/core/training_coordinator.py`
  - `agents/workflow_orchestrator/engine.py`
  - `agents/workflow_orchestrator/runtime_config.py`
- Acceptance criteria:
  - Recommendations are reproducible from stored inputs.
  - Publication gates unchanged in shadow mode.

### E5-T3: Guarded Active Mode with Bounded Deltas

- Owner: Workflow + Platform
- Depends on: E5-T2
- Scope:
  - Apply bounded ranking deltas with cooldowns and max daily movement.
  - Auto-rollback on quality/diversity regression.
- File targets:
  - `agents/workflow_orchestrator/engine.py`
  - `agents/workflow_orchestrator/runtime_config.py`
- Acceptance criteria:
  - Learner cannot mutate hard publication gate logic.
  - Rollback triggers automatically on threshold breach.

## Epic 6: Anti-Poisoning + Incident Operations

### E6-T1: Anomaly Detection and Quarantine

- Owner: Analytics + Workflow
- Depends on: E5-T1
- Scope:
  - Detect correction floods, quality spikes, domain churn, and volatility anomalies.
  - Add quarantine path that blocks promotions until clearance.
- File targets:
  - `agents/analytics/analytics_engine.py`
  - `agents/workflow_orchestrator/policies.py`
- Acceptance criteria:
  - High-risk patterns trigger quarantine automatically.
  - Quarantineed sources have no lane influence.

### E6-T2: Incident Runbooks and Drills

- Owner: Ops + Platform
- Depends on: E6-T1
- Scope:
  - Add runbooks for discovery flood, poisoning, regional collapse, and learner drift.
  - Add rollback drill checklists and evidence templates.
- File targets:
  - `docs/operations/README.md`
  - `docs/operations/` (new runbooks)
- Acceptance criteria:
  - Team can execute whitelist-only fallback in defined RTO.
  - Runbooks include exact command/API sequences and owner handoff.

## Epic 7: Observability + Transparency

### E7-T1: Governance KPI Dashboard Pack

- Owner: Analytics
- Depends on: E3-T2, E4-T2, E6-T1
- Scope:
  - Add KPI panels for intake/rejection/promotion/demotion/global spread/concentration/starvation risk.
- File targets:
  - `agents/analytics/analytics_engine.py`
- Acceptance criteria:
  - KPIs support canary go/no-go at each rollout stage.

### E7-T2: Transparency Payload Extensions (Optional)

- Owner: Dashboard + Publisher
- Depends on: E4-T2
- Scope:
  - Add source governance explainability payload (state, transition reason, score version) for sampled outputs.
- File targets:
  - `agents/dashboard/transparency_repository.py`
- Acceptance criteria:
  - Internal transparency payloads expose governance provenance for sampled records.

## Epic 8: Rollout + Sign-Off

### E8-T1: Canary Rollout Ladder

- Owner: Release + Platform
- Depends on: E7-T1
- Scope:
  - Define discovery budget ramp with hard hold gates at each stage.
  - Automate gate checks for quality, diversity, and latency SLOs.
- File targets:
  - `docs/operations/` (new rollout guide)
  - `agents/workflow_orchestrator/runtime_config.py`
- Acceptance criteria:
  - No stage advancement without consecutive healthy windows.
  - Stage failure auto-holds or rolls back based on policy.

### E8-T2: Production Sign-Off Bundle

- Owner: Program + Tech Leads
- Depends on: E8-T1
- Scope:
  - Produce final readiness artifact with tests, drill evidence, anomaly outcomes, and approvals.
- File targets:
  - `docs/operations/README.md`
  - `docs/operations/` (new sign-off checklist)
- Acceptance criteria:
  - Critical and high-risk checks green.
  - Cross-functional sign-off recorded.

## Cross-Cutting Program Gates

1. Safety gate: rollback to whitelist-only validated for every release candidate.
2. Flood gate: discovery cannot exceed budget caps under adversarial intake.
3. Integrity gate: every transition and score update has immutable provenance.
4. Publication gate: discovery signals cannot bypass factual corroboration policies.
5. Diversity gate: floors/ceilings enforced continuously for global spread.
6. Learning gate: model-driven ranking remains bounded, auditable, and reversible.

## Critical Path and Parallel Tracks

1. Critical path: Epic 0 -> Epic 1 -> Epic 2 -> Epic 3 -> Epic 4 -> Epic 8.
2. Parallel track A (Data): Epic 1 + Epic 5 data foundations.
3. Parallel track B (Observability): Epic 0 metrics + Epic 6 + Epic 7 dashboards.
4. Parallel track C (Ops): Incident and rollout runbook authoring.
5. Hard blocker: Epic 5 active mode cannot start until Epic 6 quarantine controls are live.

## Program Definition of Done

1. Hybrid whitelist+discovery behavior is operational with enforced lifecycle states.
2. Rollback and kill switches validated in load drills.
3. Factual quality SLOs are not degraded versus baseline.
4. Global spread improves without concentration regressions.
5. Poisoning simulations cannot force unsafe promotions.
6. On-call playbooks and dashboards are sufficient for rapid diagnosis and recovery.