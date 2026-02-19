# Ingestion → Analysis Remediation Log

## Session: 2026-02-18 (Phase 0 Baseline)

### Scope
- Runbook followed: `docs/operations/INGESTION_TO_ANALYSIS_BACKLOG_RUNBOOK.md`
- Phase executed: **Phase 0 — Baseline and Guardrails**
- Behavior/config/code changes applied: **None**

### 0.1 Canonical baseline checks
Command:
```bash
set -a && source /app/global.env && set +a
/app/.venv/bin/python /app/canonical_status_check.py
/app/.venv/bin/python /app/check_workflow_progress.py
/app/.venv/bin/python /app/final_pipeline_status.py
```

Results:
- `canonical_status_check.py`: **System Status 🟢 GO** (13/13 OK)
- `check_workflow_progress.py`:
  - `Total Articles: 2236`
  - `Sources Crawled: 269/274`
  - `Sources With Articles: 202/274`
  - `Analyzed: 1079`
  - `Embedded: 2236`
- `final_pipeline_status.py`:
  - `Crawl Tasks: 67`
  - `Articles Found: 2236`
  - `Articles Ingested: 2236`
  - `Documents Embedded: 2236`
  - `Timestamp: 2026-02-18 14:13:43`

### 0.2 Backlog and throughput metrics
Command:
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

Results:
- `backlog_analyzed0= 1157`
- `newly_analyzed_last60m= 131`

### 0.3 Reliability baseline (log-derived)
Command:
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

Results:
- `analyst_requests= 181`
- `mysql_disconnect_errors= 16`
- `error_rate_pct= 8.84`

### Phase 0 checkpoint
- Baseline metrics captured and timestamped: ✅
- Rollback owner identified: ✅ **Current operator (session user)**

### Notes
- No remediation actions were applied in this phase.
- Next step (after rollback owner assignment): begin **Phase 1 (config-only throughput lift)** with 15-minute observation windows per runbook.

---

## Session: 2026-02-18 (Phase 1 Blocker Resolution)

### Phase 1 blocker observed
- Symptom: `workflow_orchestrator /status` repeatedly reported defaults (`polling_interval_seconds=10`, `max_concurrent_tasks=5`) after restart.
- Symptom: `config/system_config.json` repeatedly lost the `orchestrator` section.

### Root cause
- Dashboard shutdown path persisted unified config through the typed config manager.
- Unified schema (`config/schemas/__init__.py`) did not include top-level `orchestrator`.
- On persistence, unknown keys were dropped from `system_config.json`, removing Phase 1 orchestrator settings.

### Changes applied
- Added `OrchestratorConfig` + `OrchestratorResourceLimitsConfig` to unified schema and added `orchestrator` to `JustNewsConfig`.
- Updated dashboard config persistence to skip no-op writes when dashboard port is unchanged.
- Re-applied Phase 1 orchestrator values in `config/system_config.json`:
  - `polling_interval_seconds: 5`
  - `max_concurrent_tasks: 10`
  - `resource_limits`: unchanged from runbook defaults.

### Verification evidence
- Full restart cycle completed (`stop_all_services.sh --skip-db` + `start_all_services.sh --skip-db --skip-migrations`).
- Post-restart file check:
  - `has_orchestrator=True` in `config/system_config.json`.
- Post-restart runtime check:
  - `http://127.0.0.1:8023/status` reports `polling_interval_seconds=5` and `max_concurrent_tasks=10`.

### Decision
- Phase 1 config persistence blocker: ✅ **resolved**.
- Next action: run the Phase 1 15-minute observation window and evaluate keep/rollback/iterate criteria per runbook.

---

## Session: 2026-02-18 (Phase 1 Observation Window #1)

### Observation setup
- Window length: 15 minutes (runbook-compliant)
- Runtime config at start (`/status`):
  - `polling_interval_seconds=5`
  - `max_concurrent_tasks=10`

### Metrics (start)
- `backlog_analyzed0=1074`
- `newly_analyzed_last60m=120`
- `fact_checks=5159`
- `synthesized_articles=869`
- `analyst_requests=12`
- `mysql_disconnect_errors=0`

### Metrics (end)
- `backlog_analyzed0=1044` (delta: **-30**)
- `newly_analyzed_last60m=104`
- `newly_analyzed_last15m=19` (approx **76/hour**)
- `fact_checks=5392` (delta: **+233**)
- `synthesized_articles=899` (delta: **+30**)
- `analyst_requests=78`
- `mysql_disconnect_errors=12`
- `analyst_error_rate_pct=15.38`

### Reliability confirmation (recent log slice)
- Recent analyst log slice (`last 800 lines`):
  - `req=28`
  - `mysql_disconnect=4`
  - `error_rate_pct=14.29`
- Repeated error observed:
  - `2055: Lost connection to MySQL server at 'mariadb:3306'`

### Runbook gate evaluation
- ✅ Backlog trended down.
- ✅ Downstream continued progressing (`fact_checks`, `synthesized_articles`).
- ❌ Analyst reliability gate failed (`>3%` for sustained checks).
- ❌ Throughput target failed (well below `>=300/hour` target).

### Decision
- **Rollback Phase 1 tuning applied** per rollback matrix.

### Rollback actions applied
- `global.env`:
  - Disabled explicit MCP Phase 1 timeout/retry overrides.
  - Set `ANALYST_WORKERS=1`.
- `config/system_config.json`:
  - Reverted orchestrator to `polling_interval_seconds=10` and `max_concurrent_tasks=5`.

### Next action
- Restart services to apply rollback values.
- Run stabilization check window before any further phase advancement.

---

## Session: 2026-02-18 (Post-Rollback Stabilization Window #1)

### Observation setup
- Window length: 15 minutes (post-rollback)
- Runtime config start/end (`/status`):
  - `polling_interval_seconds=10`
  - `max_concurrent_tasks=5`
- Analyst worker setting confirmed on startup: `ANALYST_WORKERS=1`

### Metrics (start)
- `backlog_analyzed0=1030`
- `newly_analyzed_last60m=87`
- `newly_analyzed_last15m=19`
- `fact_checks=5505`
- `synthesized_articles=904`
- `analyst_requests=10`
- `mysql_disconnect_errors=0`

### Metrics (end)
- `backlog_analyzed0=1011` (delta: **-19**)
- `newly_analyzed_last60m=69`
- `newly_analyzed_last15m=18` (approx **72/hour**)
- `fact_checks=5674` (delta: **+169**)
- `synthesized_articles=922` (delta: **+18**)
- `analyst_requests=32`
- `mysql_disconnect_errors=6`
- `analyst_error_rate_pct=18.75`

### Reliability confirmation (recent slice)
- Recent analyst log slice (`last 600 lines`):
  - `req=27`
  - `mysql_disconnect=6`
  - `error_rate_pct=22.22`

### Gate evaluation
- ✅ Backlog continued to decrease.
- ✅ Downstream stages continued advancing.
- ❌ Reliability still failing badly (disconnect/error rate far above threshold).
- ❌ Throughput still below target.

### Decision
- Post-rollback stabilization is **not sufficient** to clear reliability gates.
- Continue with runbook escalation path: prioritize **Phase 3 (DB resilience in analyst path)** before any new throughput increases.

---

## Session: 2026-02-18 (Phase 3 Implementation)

### Scope
- Runbook section implemented: **Phase 3 — DB resilience in analyst path**
- Target file: `agents/analyst/tools.py`

### Changes applied
1. **Per-call cursor/connection handling in `analyze_article` path**
   - Replaced direct `db.mb_conn.cursor()` usage with compatibility-safe per-call acquisition:
     - `_acquire_cursor(..., per_call semantics via get_safe_cursor)`
     - `_close_cursor_conn(...)` with safe close behavior for non-shared connections.

2. **Transient DB retry wrapper for critical operations**
   - Added retry logic for MySQL transient disconnect classes:
     - error codes: `2006`, `2013`, `2055`
   - Applied to:
     - article fetch (`_fetch_article_row_with_retry`)
     - article update/commit (`_execute_update_with_retry`)
   - Backoff: incremental short sleep (`0.2s * attempt`), max 2 retries.

3. **Idempotence enforcement**
   - Before analysis, fetch now includes `analyzed` flag.
   - If `analyzed=1`, returns success no-op:
     - `{..., "no_op": true, "reason": "already analyzed"}`
   - Preserved update write shape for analyzed path:
     - `structured_metadata`
     - `factual_accuracy_score`
     - `fact_check_details`
     - `updated_at = NOW()`

4. **Structured metadata safety**
   - Added resilient JSON parse fallback for existing `structured_metadata`.

### Runtime activation
- Restarted stack (`stop_all_services.sh --skip-db` + `start_all_services.sh --skip-db --skip-migrations`).
- Analyst confirmed running with current baseline worker count (`ANALYST_WORKERS=1`).

### Verification evidence
1. **Idempotence no-op validation**
   - Call: `/analyze_article` on already analyzed article `2237`
   - Response: `status=200` with `no_op=true`, `reason="already analyzed"`.

2. **Normal analyzed-write path validation**
   - Call: `/analyze_article` on unanalyzed article `189`
   - Response: `status=200`, `analysis_result.status="success"`.
   - DB post-check for article `189`:
     - `analyzed=1`
     - `factual_accuracy_score=0.5`
     - `fact_check_details IS NOT NULL = 1`
     - `structured_metadata IS NOT NULL = 1`

### Decision
- **Phase 3 implementation complete and deployed.**
- Next step: run a new 15-minute observation window focused on MySQL disconnect/error rate reduction before any new throughput tuning.

---

## Session: 2026-02-18 (Phase 3 Validation Window #1)

### Observation setup
- Window length: 15 minutes
- Runtime config start/end (`/status`):
  - `polling_interval_seconds=10`
  - `max_concurrent_tasks=5`

### Metrics (start)
- `backlog_analyzed0=993`
- `newly_analyzed_last60m=76`
- `newly_analyzed_last15m=21`
- `fact_checks=5777`
- `synthesized_articles=934`
- `analyst_requests=7`
- `mysql_disconnect_errors=0`
- `analyst_error_rate_pct=0.00`

### Metrics (end)
- `backlog_analyzed0=963` (delta: **-30**)
- `newly_analyzed_last60m=76`
- `newly_analyzed_last15m=20` (approx **80/hour**)
- `fact_checks=5995` (delta: **+218**)
- `synthesized_articles=961` (delta: **+27**)
- `analyst_requests=37`
- `mysql_disconnect_errors=0`
- `analyst_error_rate_pct=0.00`

### Reliability confirmation (recent slice)
- Recent analyst log slice (`last 700 lines`):
  - `req=27`
  - `mysql_disconnect=0`
  - `error_rate_pct=0.00`

### Gate evaluation
- ✅ MySQL disconnect errors reduced to zero in observed window.
- ✅ Analyst reliability improved to 0% disconnect-derived error rate in-window and recent slice.
- ✅ Backlog continued to drain.
- ✅ Downstream progression remained healthy.

### Decision
- **Phase 3 accepted** (DB resilience fix effective).
- Next recommended step: re-enter **Phase 1 config-only throughput lift** cautiously (single increment + 15-minute gate) now that reliability baseline is stable.

---

## Session: 2026-02-18 (Retune #1 after Phase 3)

### Change applied
- Single controlled increment:
  - `orchestrator.polling_interval_seconds: 10 -> 8`
  - `max_concurrent_tasks` unchanged at `5`
  - `ANALYST_WORKERS` unchanged at `1`

### Runtime verification
- `/status` confirmed start/end config:
  - `polling_interval_seconds=8`
  - `max_concurrent_tasks=5`

### Metrics (start)
- `backlog_analyzed0=920`
- `newly_analyzed_last60m=79`
- `newly_analyzed_last15m=18`
- `fact_checks=6304`
- `synthesized_articles=992`
- `analyst_requests=4`
- `mysql_disconnect_errors=0`

### Metrics (end)
- `backlog_analyzed0=898` (delta: **-22**)
- `newly_analyzed_last60m=83`
- `newly_analyzed_last15m=21` (approx **84/hour**)
- `fact_checks=6440` (delta: **+136**)
- `synthesized_articles=1015` (delta: **+23**)
- `analyst_requests=26`
- `mysql_disconnect_errors=0`
- `analyst_error_rate_pct=0.00`

### Reliability confirmation (recent slice)
- `req=27`, `mysql_disconnect=0`, `error_rate_pct=0.00`

### Gate evaluation
- ✅ Reliability maintained (no disconnect regression).
- ✅ Backlog continued to drain.
- ✅ Downstream continued to advance.

### Decision
- **Retune #1 accepted and kept**.
- Next cautious step (optional): `max_concurrent_tasks 5 -> 6` with unchanged polling (`8`) and another 15-minute gate.

---

## Session: 2026-02-18 (Retune #2 after Phase 3)

### Change applied
- Single controlled increment:
  - `orchestrator.max_concurrent_tasks: 5 -> 6`
  - `polling_interval_seconds` unchanged at `8`
  - `ANALYST_WORKERS` unchanged at `1`

### Runtime verification
- `/status` confirmed start/end config:
  - `polling_interval_seconds=8`
  - `max_concurrent_tasks=6`

### Metrics (start)
- `backlog_analyzed0=888`
- `newly_analyzed_last60m=81`
- `newly_analyzed_last15m=24`
- `fact_checks=6486`
- `synthesized_articles=1018`
- `analyst_requests=4`
- `mysql_disconnect_errors=0`

### Metrics (end)
- `backlog_analyzed0=863` (delta: **-25**)
- `newly_analyzed_last60m=85`
- `newly_analyzed_last15m=22` (approx **88/hour**)
- `fact_checks=6642` (delta: **+156**)
- `synthesized_articles=1036` (delta: **+18**)
- `analyst_requests=29`
- `mysql_disconnect_errors=0`
- `analyst_error_rate_pct=0.00`

### Reliability confirmation (recent slice)
- `req=28`, `mysql_disconnect=0`, `error_rate_pct=0.00`

### Gate evaluation
- ✅ Reliability maintained (no disconnect regression).
- ✅ Backlog continued to drain.
- ✅ Downstream progression remained healthy.

### Decision
- **Retune #2 accepted and kept**.
- Next cautious step (optional): `max_concurrent_tasks 6 -> 7` with unchanged polling (`8`) and another 15-minute gate.
