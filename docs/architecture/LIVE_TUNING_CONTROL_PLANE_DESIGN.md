# Live Tuning Control Plane Design (JustNews)

Date: 2026-02-19  
Status: Proposed (MVP-ready)

## Related Planning Package

- [AUTONOMIC_ORCHESTRATOR_ARCHITECTURE.md](AUTONOMIC_ORCHESTRATOR_ARCHITECTURE.md)
- [AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md](AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md)
- [AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md](AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md)
- [../operations/AUTONOMIC_ORCHESTRATOR_RUNBOOK.md](../operations/AUTONOMIC_ORCHESTRATOR_RUNBOOK.md)

## 1) Objective

Enable **live tuning** of system speed/accuracy/reliability knobs across JustNews without restarting the full stack, while preserving safety, consistency, and auditability.

Primary outcomes:
- Faster optimization loops during backlog drain and production incidents.
- Deterministic, auditable runtime configuration changes.
- Clear separation between **hot-reloadable** and **restart-required** settings.

---

## 2) Problem Statement (Current State)

Current config behavior is mixed:
- Many services read env vars at process startup and cache constants (for example, fact-check shim timeout/retry/circuit settings).
- Workflow orchestrator reads `config/system_config.json` at startup into in-memory state.
- Policy behavior also reads some env variables directly during runtime checks.

Observed impact:
- Operational tuning often requires service or stack restart.
- Partial changes can produce inconsistent behavior between agents.
- Rename/semantic drift (e.g., policy naming) increases operator confusion.

---

## 3) Design Principles

1. **Single runtime source of truth** for tunable settings.
2. **Hybrid config model**: startup defaults from env/file + runtime overrides from control plane.
3. **Per-setting safety contract**: hot-reloadable vs restart-required.
4. **Versioned, atomic updates** with validation and rollback.
5. **Observable effective config** per service.
6. **Fail-safe behavior**: bad runtime updates must not destabilize agents.

---

## 4) Proposed Architecture

## 4.1 Control Plane Components

1. **Runtime Config Store** (authoritative for live overrides)
   - Preferred MVP backend: Redis (already available in stack).
   - Fallback option: MariaDB table.

2. **Config Schema Registry**
   - Defines each tunable key, type, min/max, default, mutability, and owner service.
   - Backed by Pydantic models for strict validation.

3. **Config API (Admin-only)**
   - Read/write endpoint(s) for operators and dashboard.
   - Supports dry-run validation before apply.

4. **Agent-side Config Client**
   - Poll or subscribe for updates.
   - Applies only keys for that service.
   - Exposes current `config_version` and effective values.

5. **Audit Log**
   - Who changed what, when, old/new values, validation result, rollback marker.

## 4.2 Data Flow

1. Operator submits update (`PATCH /runtime-config`).
2. API validates against schema + safety rules.
3. Store writes new version atomically (`config_version += 1`).
4. Services fetch new version (or receive pub/sub event).
5. Each service applies hot-safe keys and reports success/failure.
6. Metrics/health endpoints expose applied version and rejected keys.

---

## 5) Configuration Model

## 5.1 Layers (Highest precedence first)

1. **Runtime Overrides** (control plane store)
2. **System Config File** (`config/system_config.json`)
3. **Environment Defaults** (`global.env` and process env)
4. **Hard-coded defaults** (final fallback)

## 5.2 Tunable Key Format

Use namespaced keys:
- `orchestrator.polling_interval_seconds`
- `orchestrator.max_concurrent_tasks`
- `fact_checker.shim.timeout_sec`
- `fact_checker.shim.max_retries`
- `fact_checker.shim.cb.failure_threshold`
- `fact_checker.search.max_queries`
- `fact_checker.search.deep_crawl_timeout_sec`
- `analyst.audit.max_claims_per_article`

## 5.3 Setting Metadata

Per key:
- `type`: int/float/bool/enum/string
- `constraints`: min/max/allowed set
- `mutability`: `hot` | `restart_required`
- `apply_mode`: `immediate` | `next_request` | `next_tick`
- `owner`: service name
- `description`: operator-facing guidance

---

## 6) Hot Reload Safety Matrix

## 6.1 Hot-Reloadable (MVP)

- Orchestrator:
  - polling interval
  - max concurrent tasks
  - resource thresholds (cpu/memory/gpu saturation)
- Fact-check shim:
  - request timeout
  - retries/backoff
  - circuit breaker thresholds/cooldown
- Fact-check backend:
  - query fanout count
  - evidence thresholds
  - deep crawl timeout
- MCP bus:
  - call timeout/retry/circuit thresholds

## 6.2 Restart-Required (explicitly not hot in MVP)

- Process worker counts (e.g., `ANALYST_WORKERS`)
- Model identity, quantization, and heavy model-loading parameters
- CUDA memory partitioning and process-level GPU startup options
- Port bindings and host URLs

---

## 7) API Contract (MVP)

## 7.1 Read Effective Config
- `GET /runtime-config`
  - Returns effective values, schema metadata, global `config_version`.

## 7.2 Validate Change
- `POST /runtime-config/validate`
  - Input: partial key/value patch.
  - Output: pass/fail, normalized values, impacted services, mutability warnings.

## 7.3 Apply Change
- `PATCH /runtime-config`
  - Input: patch + reason.
  - Behavior: atomic write + version increment.
  - Output: new version + impacted services.

## 7.4 Rollback
- `POST /runtime-config/rollback`
  - Input: target version.
  - Output: rollback status + new version.

---

## 8) Service Integration Pattern

Each service adds a small RuntimeConfigManager:

- On startup:
  - Load baseline from current env/config.
  - Load runtime override snapshot.
- In background loop (for example, every 2–5 seconds):
  - Check current `config_version`.
  - If changed, fetch and validate owned keys.
  - Apply hot-safe values under lock.
- Expose:
  - `/config` endpoint with:
    - `applied_version`
    - `last_apply_status`
    - `effective_values` (owned keys)

Apply semantics:
- `next_tick`: orchestrator values apply at next loop cycle.
- `next_request`: request-scoped settings apply to new requests only.
- Never mutate in-flight request parameters mid-execution.

---

## 9) Consistency & Failure Handling

1. **Atomic updates**: single versioned object write.
2. **Per-service apply ack**: success/failure with reason.
3. **Graceful reject**: invalid values are rejected before write.
4. **Stale read protection**: services compare local vs store version.
5. **Degradation policy**:
   - If config store unavailable, continue with last known good config.
   - Emit alert when staleness exceeds threshold (for example, 60s).

---

## 10) Security & Governance

- Admin-only API behind authn/authz.
- Mandatory change reason field.
- Immutable audit log entries.
- Optional approval gate for production-critical keys.
- Rate-limit config writes to avoid oscillation.

---

## 11) Observability

Metrics:
- `runtime_config_apply_success_total{service}`
- `runtime_config_apply_failure_total{service}`
- `runtime_config_version{service}`
- `runtime_config_staleness_seconds{service}`
- `runtime_config_rejected_updates_total{key}`

Logs:
- structured log on every apply/reject/rollback.

Dashboard panel suggestions:
- Effective config by service
- Version propagation lag
- Recent config changes with throughput impact overlay

---

## 12) Phased Rollout Plan

## Phase 0 — Inventory & Classification (1–2 days)
- Enumerate all speed/accuracy/reliability knobs.
- Mark each key as `hot` or `restart_required`.
- Publish canonical key registry.

## Phase 1 — Control Plane MVP (2–4 days)
- Implement runtime store + schema + validate/apply/rollback APIs.
- Add audit trail and auth guard.

## Phase 2 — First Integrations (2–4 days)
- Integrate orchestrator and fact-check shim first (highest operator value).
- Add `/config` endpoints and apply status metrics.

## Phase 3 — Expansion (3–5 days)
- Integrate MCP bus + fact-check backend + selected analyst request-time knobs.
- Add dashboard controls and alerts.

## Phase 4 — Hardening (ongoing)
- Canary updates for sensitive keys.
- Automated rollback on SLO regression.

---

## 13) MVP Key Set (Recommended)

1. `orchestrator.polling_interval_seconds` (hot)
2. `orchestrator.max_concurrent_tasks` (hot)
3. `orchestrator.resource_limits.max_gpu_memory_percent` (hot)
4. `mcp_bus.call.read_timeout_sec` (hot)
5. `mcp_bus.call.max_retries` (hot)
6. `fact_checker.shim.timeout_sec` (hot)
7. `fact_checker.shim.max_retries` (hot)
8. `fact_checker.shim.cb.failure_threshold` (hot)
9. `fact_checker.search.max_queries` (hot)
10. `fact_checker.search.deep_crawl_timeout_sec` (hot)
11. `analyst.workers` (restart_required)
12. `analyst.model.name` (restart_required)

---

## 14) Risks and Mitigations

- **Risk**: Operator over-tuning creates oscillation.
  - Mitigation: write rate limits, cooldown windows, SLO guardrails.

- **Risk**: Partial adoption causes mixed behavior.
  - Mitigation: `/config` visibility, rollout by service, explicit unsupported-key responses.

- **Risk**: Store outage blocks updates.
  - Mitigation: last-known-good cache + staleness alerts.

---

## 15) Success Criteria

- 90% of routine performance tuning changes applied without restart.
- Config propagation to all integrated services within 5 seconds.
- Zero invalid updates applied to runtime.
- Mean time to tune/recover reduced by at least 50% in backlog operations.

---

## 16) Notes for JustNews Context

- This design intentionally keeps `global.env` as baseline/bootstrap, not live source-of-truth.
- Existing `ConfigurationManager` and GPU config patterns can be reused for schema validation and reload mechanics.
- Worker scaling remains restart-based in MVP; live tuning focuses first on orchestrator/fact-check/MCP knobs where most runtime gains are currently realized.
