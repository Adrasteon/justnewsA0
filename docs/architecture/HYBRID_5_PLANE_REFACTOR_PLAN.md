# Hybrid 5-Plane Topology Refactor Plan

> Historical context note: This document may describe legacy startup/orchestration flows captured at the time. Canonical runtime for JustNews is Docker-first. See `docs/operations/DOCKER_FIRST_STRATEGY.md` and `docs/operations/DOCKER_CANONICAL_COMMANDS.md`.


Date: 2026-02-17  
Status: Proposed (implementation-ready)

## 1) Objective

Refactor service orchestration into a **hybrid 5-plane topology** that improves:

- **Accuracy**: deterministic data/model routing, explicit dependency contracts, fewer hidden runtime states.
- **Robustness**: reduced failure blast radius, strict health-gated startup, predictable restart behavior.
- **Speed**: maintain low-latency hot path, avoid model duplication, reduce unnecessary cold-start overhead.

This plan intentionally avoids full per-agent containerization in the first pass to prevent orchestration bloat and startup latency regressions.

---

## 2) Target Topology

### Plane A — Foundation (stateful/shared infra)

Services:
- `mariadb`
- `chromadb`
- `redis`
- `vllm`
- `mcp_bus`

Role:
- shared persistence + inference + coordination backbone.

Hard requirements:
- startup and readiness of all Plane A services before any downstream plane.
- canonical endpoint/env definitions for all consumers.

### Plane B — Control

Services:
- `workflow_orchestrator`
- `gpu_orchestrator`
- `crawler_control`

Role:
- scheduling, gating, control-loop decisions.

Hard requirements:
- must start after Plane A, before Data/IO plane.
- must expose explicit readiness for downstream dependency checks.

### Plane C — Data/IO

Services:
- `crawler`
- `memory`
- `fact_checker` backend (external service already containerized)

Role:
- highest external IO and data mutation paths.

Hard requirements:
- strict retries/backoff/circuit behavior.
- bounded write-path failure semantics.

### Plane D — Editorial Compute (shared worker pool)

Services:
- `chief_editor`
- `analyst`
- `synthesizer`
- `critic`
- `reasoning`
- `newsreader`
- `journalist` (and similarly shaped generation agents)

Role:
- content generation and reasoning workloads using shared inference endpoint.

Hard requirements:
- centralized model endpoint (`vllm`) only.
- no per-agent model loading duplication.

### Plane E — Presentation/Support

Services:
- `dashboard`
- `analytics`
- `archive`
- HITL/aux support services

Role:
- non-core rendering/ops support.

Hard requirements:
- should not block core publish path startup on transient failures.

---

## 3) Baseline Evidence (Current Workspace)

Primary references used for this plan:

- Canonical agent manifest: `infrastructure/agents_manifest.sh`
- Canonical startup orchestration: `start_all_services.sh`
- Active devcontainer runtime composition: `.devcontainer/docker-compose.yaml`
- Devcontainer lifecycle hooks: `.devcontainer/devcontainer.json`
- Systemd startup/restart behavior: `infrastructure/systemd/units/justnews@.service`
- Existing fact-check split architecture: `agents/fact_checker/shim.py`, `mcp_fact_checker_server/app/main.py`
- vLLM centralization guidance: `docs/operations/VLLM_QWEN_SETUP.md`
- Startup/ops runbook surface: `docs/operations/STARTUP_CHECKLIST.md`

---

## 4) Design Principles

1. **Single model-serving authority**
	 - Keep one shared vLLM endpoint for agent inference.
	 - Do not introduce per-agent model servers unless explicitly benchmark-justified.

2. **Health-gated plane progression**
	 - Plane N+1 cannot start until Plane N passes mandatory readiness checks.

3. **Manifest-first orchestration**
	 - Preserve manifest-driven identity/port definitions as source of truth.

4. **Idempotent startup and recovery**
	 - Startup routines must be safely re-runnable without destructive side effects.

5. **Explicit failure policy per plane**
	 - classify failures as hard-blocking vs soft-degraded and enforce uniformly.

6. **Progressive migration**
	 - no “big bang” cutover; phase delivery with measurable success gates.

---

## 5) Detailed Refactor Work Plan

## Phase 0 — Alignment & Freeze (1–2 days)

Goals:
- freeze canonical topology assumptions before code changes.

Tasks:
- reconcile service/port map across:
	- `infrastructure/agents_manifest.sh`
	- `docs/canonical_port_mapping.md`
	- startup scripts and env docs.
- define canonical naming convention for planes, startup states, and health labels.
- produce migration guardrails (what cannot change in Phase 1):
	- no endpoint renames,
	- no protocol changes,
	- no DB schema changes.

Deliverables:
- topology contract section added to this plan + linked in ops docs.

Exit criteria:
- one approved source of truth for service identity, ports, and startup order.

---

## Phase 1 — Plane Contracts & Health Gates (2–4 days)

Goals:
- formalize readiness contracts and enforce startup order by plane.

Tasks:
- refactor `start_all_services.sh` into explicit plane sections:
	- Plane A bootstrap + checks,
	- Plane B bootstrap + checks,
	- Plane C bootstrap + checks,
	- Plane D bootstrap + checks,
	- Plane E bootstrap + checks.
- add strict gate function(s):
	- `require_plane_ready <plane>`
	- hard fail on mandatory Plane A/B dependencies.
- codify soft-degraded behavior for Plane E.
- include structured summary output:
	- per-plane status,
	- blocker reason,
	- retry suggestion.

Deliverables:
- startup script with deterministic plane ordering and explicit gate checks.

Exit criteria:
- `--dry-run` prints deterministic 5-plane execution order.
- startup aborts if mandatory upstream plane readiness fails.

---

## Phase 2 — Foundation & Control Hardening (3–5 days)

Goals:
- stabilize highest-leverage reliability surfaces.

Tasks:
- Plane A:
	- standardize readiness checks for `mariadb`, `chromadb`, `redis`, `vllm`, `mcp_bus`.
	- ensure health probes are aligned between devcontainer and startup scripts.
- Plane B:
	- add/normalize readiness probes for `workflow_orchestrator`, `gpu_orchestrator`, `crawler_control`.
	- enforce control-plane availability before Data/IO startup.
- ensure restart semantics are consistent with systemd policy expectations.

Deliverables:
- robust foundation/control startup and recovery behavior.

Exit criteria:
- restart of a Plane B service does not require full system restart.
- mcp bus restarts recover registrations automatically within expected window.

---

## Phase 3 — Data/IO Isolation and Contract Tightening (3–6 days)

Goals:
- reduce blast radius on high-mutation paths while protecting latency.

Tasks:
- formalize fact-check pathway contract:
	- shim-to-backend behavior,
	- timeout and retry boundaries,
	- persisted result guarantees.
- audit and normalize Data/IO retry/circuit behavior (`crawler`, `memory`, fact-check path).
- add service-level guardrails for write-path failures:
	- bounded retries,
	- idempotent writes where possible,
	- explicit dead-letter/error status handling.

Deliverables:
- Data/IO plane with predictable failure and recovery semantics.

Exit criteria:
- forced failure of one Data/IO service does not cascade into Plane A/B outage.

---

## Phase 4 — Editorial Compute Pool Optimization (2–4 days)

Goals:
- maximize throughput and responsiveness without container sprawl.

Tasks:
- keep editorial agents in shared runtime pool.
- add per-agent concurrency and timeout defaults tuned for shared vLLM.
- reduce startup serialization where safe (controlled parallel starts in Plane D).
- ensure editorial agents treat Data/IO dependencies as remote contracts, not implicit local assumptions.

Deliverables:
- lower editorial startup latency and stable throughput under load.

Exit criteria:
- no model duplication introduced.
- p95 editorial response time stable or improved vs baseline.

---

## Phase 5 — Presentation/Support Isolation Policy (1–2 days)

Goals:
- keep support surfaces from blocking core pipeline reliability.

Tasks:
- classify Plane E services as non-blocking for core publish path.
- enforce optional startup mode and degraded-health reporting for Plane E.
- ensure dashboard/analytics failures do not block Planes A–D.

Deliverables:
- clear non-blocking behavior for support services.

Exit criteria:
- core ingestion/synthesis/fact-check path runs with Plane E down.

---

## Phase 6 — Validation, Perf Baseline, and Rollout (2–4 days)

Goals:
- confirm correctness and performance before full adoption.

Tasks:
- define and capture before/after metrics:
	- startup time by plane,
	- p95 latency by critical endpoint,
	- restart recovery time,
	- error rates by plane.
- update integration tests for plane-based startup assumptions.
- run staged rollout:
	- devcontainer validation,
	- integration environment validation,
	- operator runbook dry-runs.

Deliverables:
- validated rollout report and sign-off checklist.

Exit criteria:
- no regression on agreed accuracy/robustness/speed thresholds.

---

## 6) File-Level Change Map

### Primary implementation files

- `start_all_services.sh`
	- restructure into plane sections + gate functions + summary output.
- `infrastructure/agents_manifest.sh`
	- annotate plane membership metadata (or companion mapping file).
- `.devcontainer/docker-compose.yaml`
	- ensure active container set aligns with Plane A + selected isolated services.
- `.devcontainer/devcontainer.json`
	- preserve idempotent pre/post hooks while ensuring topology-compatible startup behavior.

### Supporting runtime files

- `stop_all_services.sh`
	- add plane-aware stop order.
- `start_agents_devcontainer.sh` (if active in current workflow)
	- align with plane ordering and readiness checks.
- relevant agent entrypoints for health/readiness consistency:
	- `agents/mcp_bus/main.py`
	- control/data plane service entrypoints.

### Documentation updates

- `docs/operations/STARTUP_CHECKLIST.md`
- `docs/operations/SERVICE_OPERATIONS.md`
- `docs/operations/MCP_BUS_HEALTH.md`
- `docs/performance-baselines.md`
- `docs/canonical_port_mapping.md`
- `docs/architecture_overview.md`

---

## 7) Risk Register and Mitigations

1. **Config drift across startup modes**
	 - Risk: devcontainer, systemd, and scripts diverge.
	 - Mitigation: canonical topology contract + shared env map + checklist-driven updates.

2. **Readiness false positives/negatives**
	 - Risk: services marked healthy too early.
	 - Mitigation: tighten probe criteria and require contract-level readiness.

3. **Latency regression from over-isolation**
	 - Risk: too many network hops/containers.
	 - Mitigation: keep Editorial Compute pooled; isolate only high-value services.

4. **Model resource contention**
	 - Risk: accidental model-serving duplication.
	 - Mitigation: enforce single vLLM authority and adapter defaults.

5. **Operator complexity increase**
	 - Risk: too many modes and exceptions.
	 - Mitigation: explicit plane-level runbooks and failure matrix.

---

## 8) Success Metrics (Must-Hit)

### Accuracy
- 100% of agents resolve to canonical service endpoints and model routes.
- no unresolved port/service mapping conflicts in docs vs manifest.

### Robustness
- startup determinism: reproducible plane status across repeated runs.
- controlled blast radius: single service restart does not cascade across unrelated planes.
- recovery SLO: core plane recovery within agreed target window.

### Speed
- startup time: no regression beyond agreed threshold; target improvement in Plane D readiness.
- p95 request latency: stable or improved on critical workflows.
- no increase in GPU memory pressure from topology changes.

---

## 9) Rollout and Rollback Strategy

### Rollout

1. deploy Phase 1 gate-only changes behind optional flag.
2. validate in devcontainer and integration test suites.
3. enable by default after passing acceptance criteria.
4. proceed plane-by-plane for hardening/isolation phases.

### Rollback

- keep previous startup path toggleable (single env flag) until Phase 6 sign-off.
- rollback trigger conditions:
	- startup failure rate above threshold,
	- p95 latency regression above threshold,
	- repeated unrecoverable gate failures.

---

## 10) Immediate Next Actions

1. approve this plan as canonical migration brief.
2. implement Phase 0 artifacts (topology contract + canonical mapping reconciliation).
3. begin Phase 1 startup gating refactor in `start_all_services.sh` with tests.

---

## 11) Non-Goals (for this migration)

- full per-agent containerization in one release.
- replacing systemd deployment path immediately.
- major DB schema redesign.
- changing external API contracts for downstream consumers.

