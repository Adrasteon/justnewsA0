# JustNews Crawler Maturity Checklist

This checklist is a living roadmap for evolving JustNews crawling from current-state reliability into enterprise-grade capability.

## Quarterly Status Artifact

Use this table as the single-page reporting artifact during monthly/quarterly reviews.

| Phase | Status | Target Date | Notes |
| :--- | :--- | :--- | :--- |
| Phase 1 — Reliability Foundation | Not Started | TBD | Define SLOs and reliability gates first |
| Phase 2 — Yield & Quality Control | Not Started | TBD | Start after Phase 1 gates are stable |
| Phase 3 — Scale & Frontier Architecture | Not Started | TBD | Requires durable frontier design decision |
| Phase 4 — Enterprise Controls | Not Started | TBD | Compliance/security hardening track |

Status options:

- `Not Started`
- `In Progress`
- `At Risk`
- `Blocked`
- `Done`

## How to use this checklist

- Treat each phase as a gate with explicit acceptance criteria.
- Track progress weekly using the KPIs in this document.
- Do not advance phases until required gates are met.
- Keep scope strict: finish reliability and observability before adding new features.

## Current-State Summary (baseline)

- ✅ Strong progress on configurable crawling, Crawl4AI profiles, and recovery improvements.
- ✅ Dedupe replacement behavior now helps hit new-article targets where possible.
- ⚠️ Remaining enterprise gaps: distributed frontier, stronger reliability semantics, extraction governance, anti-blocking depth, compliance automation, and SLO discipline.

---

## Phase 1 — Reliability Foundation (Now)

### Goal
Create predictable crawl outcomes and stable operations under restarts, duplicates, and transient failures.

### Checklist
- [ ] Define crawler SLOs (success rate, freshness lag, time-to-ingest, error budget).
- [ ] Add idempotency keys for all ingest writes and crawler job transitions.
- [ ] Add dead-letter handling for repeatedly failing crawl jobs.
- [ ] Add explicit retry/backoff policies per failure class (network, parsing, anti-bot, DB).
- [ ] Implement durable job lifecycle audit log (queued, running, partial, completed, failed, cancelled).
- [ ] Add runbook-backed alerting for crawl stalls and ingestion starvation.

### Acceptance Criteria
- ≥ 99% crawl job completion without manual intervention over 7 days.
- ≤ 1% orphaned/ambiguous job states after restart tests.
- Mean recovery time from crawler restart < 5 minutes.

### KPIs
- Job completion rate
- Restart recovery success rate
- Duplicate skip ratio vs final new-article yield
- Crawl-to-ingest latency p50/p95

---

## Phase 2 — Yield & Quality Control (Next)

### Goal
Maximize new useful article yield while controlling duplication and extraction drift.

### Checklist
- [ ] Add near-duplicate detection (simhash/minhash) beyond URL-hash dedupe.
- [ ] Add canonical article selection across mirrored/republished sources.
- [ ] Build extraction quality regression suite with gold pages per top domains.
- [ ] Add automated selector drift detection and profile health scoring.
- [ ] Track and enforce per-domain minimum quality thresholds.
- [ ] Add adaptive recrawl strategy by domain freshness and historical yield.

### Acceptance Criteria
- New-article yield improves ≥ 20% at same crawl cost for top 20 domains.
- Extraction regression suite pass rate ≥ 95% on every release.
- Near-duplicate false positive/negative rates within agreed thresholds.

### KPIs
- New-article yield per 1,000 fetches
- Duplicate + near-duplicate rates
- Extraction quality score by domain
- Cost per accepted article

---

## Phase 3 — Scale & Frontier Architecture (Next/Later)

### Goal
Move from site-job crawling to enterprise-grade distributed crawling control.

### Checklist
- [ ] Implement a durable distributed URL frontier (priority queue + host politeness).
- [ ] Add shard-aware scheduler and worker coordination.
- [ ] Add recrawl policy engine (freshness SLA, source priority, event-driven boosts).
- [ ] Add host-level concurrency controls and adaptive throttling.
- [ ] Add queue backpressure controls and global throughput governance.
- [ ] Add cross-region/zone failover plan for crawler workloads.

### Acceptance Criteria
- Frontier recovers without loss after coordinator restart/failover drills.
- No host politeness violations in synthetic stress tests.
- Throughput scales linearly (or near-linear) across added workers for target workloads.

### KPIs
- Frontier backlog age
- Host politeness violations
- Worker utilization
- Crawl throughput per worker

---

## Phase 4 — Enterprise Controls (Later)

### Goal
Harden JustNews for enterprise governance, compliance, and sustained operations.

### Checklist
- [ ] Add policy engine for robots/TOS/licensing rules per source.
- [ ] Add retention/deletion controls and auditable data lineage.
- [ ] Add role-based operational controls for crawl parameter changes.
- [ ] Add security hardening for crawler runtime and secret handling.
- [ ] Add compliance evidence export (who crawled what/when/why).
- [ ] Add formal capacity planning and quarterly resilience game-days.

### Acceptance Criteria
- Compliance controls verified in internal audit simulation.
- Critical operations have dual-control or approval workflow.
- Security findings for crawler tier are tracked and remediated within SLA.

### KPIs
- Compliance policy violation count
- Security findings by severity and age
- Change failure rate (crawler config changes)
- Incident count and MTTR

---

## Recommended Execution Cadence

- Weekly: KPI review + blocked items triage.
- Bi-weekly: one reliability hardening sprint item and one yield optimization item.
- Monthly: restart/failover drill + extraction regression report.
- Quarterly: maturity gate review and phase advancement decision.

## Owner Template

- Technical owner:
- Operations owner:
- Data quality owner:
- Security/compliance owner:
- Next gate target date:
