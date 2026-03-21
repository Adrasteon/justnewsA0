# Hybrid Whitelist + Discovery Execution Checklist

Date: 2026-03-21
Status: Tracking template
Companion: `HYBRID_WHITELIST_DISCOVERY_IMPLEMENTATION_TICKETS_2026-03-21.md`

## How to Use

1. Mark each line item complete only after artifact evidence is attached.
2. Do not advance canary stages unless all mandatory gates are green.
3. If any critical gate fails, execute rollback and open an incident artifact.

## Phase Gate A: Safety Baseline (Must Pass Before Any Discovery Enablement)

- [ ] Kill switches implemented and validated under active crawl load.
- [ ] Whitelist-only fallback tested and restores baseline behavior.
- [ ] Runtime config audit trail confirms apply and rollback lineage.
- [ ] Baseline SLO window captured for quality, diversity, latency, and error rate.

Evidence links:
- [ ] Runtime config API logs
- [ ] Rollback drill output
- [ ] Baseline dashboard snapshot

## Phase Gate B: Lifecycle State Enforcement

- [ ] Source lifecycle schema migration applied and verified.
- [ ] Transition audit records include actor, reason, old/new state, timestamp.
- [ ] State-aware source eligibility enforced in crawler and policy paths.
- [ ] Invalid transitions rejected and logged.

Evidence links:
- [ ] Migration evidence
- [ ] DB integrity checks
- [ ] Transition test results

## Phase Gate C: Discovery Intake Guardrails

- [ ] Discovery profile limits configured (depth, per-page links, per-domain caps).
- [ ] Off-site follow is disabled outside discovery profile.
- [ ] Domain normalization and dedupe queue are operational.
- [ ] Provenance fields present for all discovered candidates.
- [ ] Hard deny filters block known low-quality domain classes pre-budget.

Evidence links:
- [ ] Discovery profile config snapshot
- [ ] Adapter/crawler integration tests
- [ ] Deny filter regression report

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
