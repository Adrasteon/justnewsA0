# Ingestion → Analysis Backlog Remediation Runbook

## Purpose
This runbook defines the exact implementation sequence to drain large `articles.analyzed = 0` backlogs safely, with measurable checkpoints and rollback triggers.

## Scope
- Pipeline segment: ingestion → analysis (and immediate downstream fact-check handoff).
- Environment: devcontainer / single-node JustNews stack.
- Primary goal: increase analysis drain rate without destabilizing downstream stages.

## Success Targets
- Drain rate: **>= 300 analyzed/hour** (initial target, can be raised after stability).
- Analyst error rate: **< 1%** over 15-minute windows.
- MySQL disconnect errors (`2055`): **0 sustained bursts**.
- No sustained increase (>20%) in MCP call p95 latency.
- No downstream deadlock (fact-check / synthesis still making forward progress).

## Safety Rules
- Apply changes in phase order only.
- Do not introduce multiple high-risk code changes in the same phase.
- Hold each phase for at least one 15-minute observation window before proceeding.
- If rollback criteria are met, revert that phase immediately and stabilize before continuing.

---

## Phase 0 — Baseline and Guardrails (No behavior changes)

### 0.1 Capture baseline snapshot
Run and store output in an ops note:

```bash
set -a && source /app/global.env && set +a
/app/.venv/bin/python /app/canonical_status_check.py
/app/.venv/bin/python /app/check_workflow_progress.py
/app/.venv/bin/python /app/final_pipeline_status.py
```

### 0.2 Capture backlog and throughput metrics

```bash
set -a && source /app/global.env && set +a && /app/.venv/bin/python - <<'PY'
import os, mysql.connector
conn=mysql.connector.connect(host=os.getenv('MARIADB_HOST','mariadb'),port=int(os.getenv('MARIADB_PORT','3306')),user=os.getenv('MARIADB_USER','justnews'),password=os.getenv('MARIADB_PASSWORD','dev_justnews_password'),database=os.getenv('MARIADB_DB','justnews'))
cur=conn.cursor()
cur.execute("SELECT COUNT(*) FROM articles WHERE analyzed=0")
print('backlog_analyzed0=', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM articles WHERE analyzed=1 AND updated_at >= (NOW() - INTERVAL 60 MINUTE)")
print('newly_analyzed_last60m=', cur.fetchone()[0])
cur.close(); conn.close()
PY
```

### 0.3 Log-derived reliability baseline

```bash
/app/.venv/bin/python - <<'PY'
import re
from pathlib import Path
log = Path('/tmp/justnews_services_logs/analyst.startup.log').read_text(errors='ignore')
req = len(re.findall(r"Received analyze_article request", log))
err = len(re.findall(r"Lost connection to MySQL server", log))
print('analyst_requests=', req)
print('mysql_disconnect_errors=', err)
print('error_rate_pct=', round((err/req)*100,2) if req else 0)
PY
```

### Exit criteria for Phase 0
- Baseline metrics captured and timestamped.
- Rollback owner identified.

---

## Phase 1 — Config-only throughput lift (Lowest risk)

## 1A. Orchestrator cadence/concurrency
Edit `config/system_config.json` under `orchestrator` (add section if absent) with initial values:

```json
"orchestrator": {
  "polling_interval_seconds": 5,
  "max_concurrent_tasks": 10,
  "resource_limits": {
    "max_cpu_percent": 95,
    "max_memory_percent": 98,
    "max_gpu_utilization": 95,
    "max_gpu_memory_percent": 95
  }
}
```

## 1B. Analyst worker parallelism
In `start_all_services.sh`, for `analyst` startup, run with workers:
- initial: `--workers 2`
- if stable after 15m: increase to `--workers 3`
- optional max in this phase: `--workers 4`

## 1C. MCP call timeout/retry tuning (env)
Add or override in `global.env` (backlog mode defaults):

```dotenv
MCP_CALL_CONNECT_TIMEOUT=2
MCP_CALL_READ_TIMEOUT=90
MCP_MAX_RETRIES=2
MCP_RETRY_BACKOFF_BASE=0.15
MCP_CB_FAIL_THRESHOLD=4
MCP_CB_COOLDOWN_SEC=8
```

### Phase 1 validation (every 15 minutes)
- `backlog_analyzed0` should trend down.
- `newly_analyzed_last60m` should increase materially from baseline.
- No spike in `HTTP 500` from analyst.

### Rollback criteria for Phase 1
Rollback this phase if any are true for 2 consecutive checks:
- analyst error rate > 3%
- MCP tool-call failures > 5% windowed
- CPU > 95% sustained or memory > 98% sustained
- downstream policies stop advancing for 15+ minutes

Rollback actions:
- Revert `max_concurrent_tasks` to previous value.
- Revert polling to previous value.
- Reduce analyst workers by 1 step.
- Restore MCP timeout/retry values.

---

## Phase 2 — Policy scheduling improvements (Medium risk, high gain)

## 2A. Prioritize ingestion policy in engine order
In `agents/workflow_orchestrator/engine.py`:
- keep `ingestion_to_analysis` first.
- ensure no long-running downstream policy blocks repeated ingestion passes for extended windows.

## 2B. Split per-policy limits
Current design uses one `max_concurrent_tasks` for every policy. Introduce per-policy limits in config, e.g.:

```json
"orchestrator": {
  "policy_limits": {
    "ingestion_to_analysis": 20,
    "analysis_to_fact_check": 10,
    "analysis_to_summary": 8,
    "analysis_to_embedding": 8,
    "incremental_clustering": 6,
    "cluster_to_synthesis": 4,
    "synthesis_to_critique": 4,
    "synthesis_to_publishing": 4
  }
}
```

Fallback behavior: if a policy limit is missing, use global `max_concurrent_tasks`.

## 2C. Backlog mode gate
Add backlog mode trigger by DB count (e.g. analyzed=0 > 500):
- temporarily apply higher ingestion limit.
- preserve minimum downstream budget to avoid starvation.

### Phase 2 validation
- Observe increased ingestion policy matches per hour.
- Confirm downstream still progresses (fact-check and publish counts continue to move).

### Rollback criteria for Phase 2
- If downstream stalls while ingestion drains, disable backlog mode and revert to Phase 1 settings.

---

## Phase 3 — DB resilience in analyst path (Targeted code fix)

## 3A. Remove shared-connection dependency in `analyze_article`
In `agents/analyst/tools.py`:
- replace direct shared `db.mb_conn.cursor()` usage with `get_safe_cursor(per_call=True, buffered=True)` or `get_connection()` per request.
- close cursor + connection in `finally` blocks.

## 3B. Add transient DB retry wrapper
For critical DB operations (fetch/update/commit):
- retry transient `mysql.connector` disconnect errors (`2006`, `2013`, `2055`) with small backoff.
- max 2 retries.

## 3C. Preserve idempotence
Before update:
- if `analyzed=1` already, return success/no-op.
- maintain existing write shape for `structured_metadata`, `factual_accuracy_score`, and `fact_check_details`.

### Phase 3 validation
- MySQL disconnect errors should drop near zero.
- duplicate analyze retries per article should shrink.

### Rollback criteria for Phase 3
- Any schema/write regression in `articles` updates.
- Rising error rate after deployment.

Rollback action: restore previous `analyze_article` implementation.

---

## Phase 4 — Optional latency control for backlog mode

Use only if backlog still drains too slowly after Phase 3.

## 4A. Factual audit cost controls (backlog mode only)
- Lower `max_claims` from 5 to 3 during backlog mode.
- Lower per-claim timeout from 60s to 30–40s.
- Keep final publication gates unchanged.

## 4B. Bounded fan-out
- Optional semaphore around audit claim verification to avoid burst overload.

### Validation
- Measure impact on analyzed/hour vs quality outputs.

### Rollback
- Restore original audit settings if quality or downstream checks regress.

---

## Phase 5 — Exit criteria and steady-state handoff

Backlog mode can be turned off when all are true:
- `articles.analyzed=0` < 200
- error rate remains < 1% for 3 consecutive checks
- no sustained MCP retry storms
- downstream publish flow remains healthy

Steady-state recommended settings after drain:
- Keep per-call DB handling (Phase 3) permanently.
- Keep moderate orchestrator concurrency (example: 8–10).
- Keep analyst workers at lowest stable value that meets SLA.

---

## Monitoring Checklist (15-minute cadence)
- [ ] `articles.analyzed=0` trend (down)
- [ ] `newly_analyzed_last60m` trend (up)
- [ ] analyst MySQL disconnect errors
- [ ] MCP analyst tool-call failures and retries
- [ ] downstream advancement (`fact_checks`, synthesis, publishing)
- [ ] CPU/memory/GPU saturation

---

## Rollback Matrix

| Symptom | Likely Cause | Immediate Action | Follow-up |
|---|---|---|---|
| Analyst 500s spike | Over-concurrency or DB instability | Reduce analyst workers by 1 step | Inspect DB connection lifecycle |
| MCP retries spike | Timeout too tight or agent saturation | Raise `MCP_CALL_READ_TIMEOUT` and/or reduce concurrency | Inspect analyst latency distribution |
| Backlog not moving | Ingestion policy under-budget | Increase `ingestion_to_analysis` limit | Re-balance policy budgets |
| Downstream stalls | Ingestion starving downstream | Enable minimum downstream quota | Tune backlog mode policy split |
| Resource saturation | Concurrency too high | Revert last increment | Increase gradually with observation window |

---

## Change Log Template (for each phase)
- Date/time:
- Phase:
- Exact values changed:
- Baseline before:
- Metrics after 15m:
- Metrics after 30m:
- Decision: keep / rollback / iterate
- Notes:
